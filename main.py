#!/usr/bin/env python3
"""
Run two iperf3 passes (normal + reverse) to collect both inbound and outbound throughput
of the remote server (node X240), then merge with OpenNMS RRD data.
- Uses SSH key (recommended) to start/stop iperf3 server on the remote node and scp logs back.
- Parses iperf3 JSON (client single-JSON and server multi-JSON) and converts relative seconds -> epoch.
- Resamples iperf3 1s intervals to RRD_RESOLUTION seconds (mean) via pandas.
- Reads OpenNMS RRD ifHCIn/OutOctets and converts to bits/s.
- Aligns time window to RRD_RESOLUTION grid and waits for OpenNMS/collectd to flush final samples.
- Writes a single CSV aligned on timestamps: rrd_in/out + iperf_server_in/out.
"""

import subprocess
import time
import json
import csv
import os
import os.path as osp
import logging
from datetime import datetime
from time import sleep

import rrdtool
import pandas as pd

# ===== CONFIG =====
REMOTE_USER = "tung196"
REMOTE_HOST = "100.71.60.46"               # X240 Tailscale IP
SSH_KEY_PATH = "~/.ssh/id_ed25519_opennms" # will be expanded
REMOTE_JSON_PATH = "/tmp/iperf3_server.json"

JSON_DIR = "json_data"
LOCAL_CLIENT_JSON = osp.join(JSON_DIR, "iperf3_client.json")   # overwritten each run
LOCAL_SERVER_JSON = "iperf3_server.json"   # temp name when scp
CSV_OUT = "merged_bits_dual.csv"
LOG_FILE = "data_fetcher.log"

IPERF_DURATION = 1800        # seconds; set 1800 for 30 minutes
IPERF_BW = "10M"            # e.g., 1M or 10M
IPERF_RESOLUTION = 1        # iperf3 report interval (seconds)

# OpenNMS RRD paths (server node X240)
RRD_IN = "/var/lib/opennms/rrd/snmp/5/wlp3s0-28b2bd35dbcb/ifHCInOctets.rrd"
RRD_OUT = "/var/lib/opennms/rrd/snmp/5/wlp3s0-28b2bd35dbcb/ifHCOutOctets.rrd"
RRD_RESOLUTION = 30         # seconds (must match your polling interval)

# --- Overhead RRD paths (OpenNMS Core localhost) ---
RRD_OVERHEAD = {
    "loadavg1": "/var/lib/opennms/rrd/snmp/1/loadavg1.rrd",
    "memAvailReal": "/var/lib/opennms/rrd/snmp/1/memAvailReal.rrd",
    "SwapOut": "/var/lib/opennms/rrd/snmp/1/SwapOut.rrd",
    "IORawSent": "/var/lib/opennms/rrd/snmp/1/IORawSent.rrd",
}
# ===================

# ---------- util helpers ----------

def setup_logging():
    """Set up logging to file and console."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler()
        ]
    )

def align_up(ts: int, step: int) -> int:
    """Round up timestamp ts to nearest multiple of step."""
    return ((ts + step - 1) // step) * step


def align_down(ts: int, step: int) -> int:
    """Round down timestamp ts to nearest multiple of step."""
    return (ts // step) * step


def get_rrd_last_update(rrd_path: str) -> int:
    """Return last update timestamp known by RRD (or 0 on error)."""
    try:
        return int(rrdtool.last(rrd_path) or 0)
    except Exception:
        return 0


# ---------- SSH helpers ----------
def _ssh_base(cmd_list):
    key = osp.expanduser(SSH_KEY_PATH)
    return ["ssh", "-i", key, f"{REMOTE_USER}@{REMOTE_HOST}"] + cmd_list


def _scp_base(src, dest):
    key = osp.expanduser(SSH_KEY_PATH)
    return ["scp", "-i", key, src, dest]


def run_ssh(cmd_str: str) -> str:
    """Run an SSH command and return stdout as string."""
    full = _ssh_base([cmd_str])
    p = subprocess.run(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        logging.error(f"SSH command failed: {p.stderr}")
        raise RuntimeError(p.stderr)
    return p.stdout.strip()


def start_server() -> str:
    # Start iperf3 server on remote in background, log JSON to REMOTE_JSON_PATH, return PID
    cmd = f"nohup iperf3 -s -i {IPERF_RESOLUTION} -J > {REMOTE_JSON_PATH} 2>&1 & echo $!"
    pid = run_ssh(cmd)
    logging.info(f"Started remote iperf3 server PID {pid}")
    return pid

def stop_server(pid: str) -> None:
    try:
        run_ssh(f"kill {pid}")
        logging.info("Stopped remote iperf3 server")
    except Exception as e:
        logging.warning(f"Warning stopping server: {e}")

def scp_server_json(dest: str) -> None:
    src = f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_JSON_PATH}"
    cmd = _scp_base(src, dest)
    subprocess.run(cmd, check=True)

# ---------- RRD fetch helper ----------
def fetch_multiple_rrd(rrd_dict, start_ts, end_ts, resolution):
    """Fetch multiple RRDs and return {metric_name: {ts: value}}"""
    results = {}
    for name, path in rrd_dict.items():
        logging.info(f"Fetching overhead RRD: {name}")
        try:
            results[name] = fetch_rrd(path, start_ts, end_ts, resolution)
        except Exception as e:
            logging.warning(f"Failed to fetch {name}: {e}")
    return results


def fetch_rrd(rrd_path: str, start_ts: int, end_ts: int, resolution: int) -> dict:
    dat = rrdtool.fetch(
        rrd_path,
        "AVERAGE",
        "--resolution", str(resolution),
        "--start", str(start_ts),
        "--end", str(end_ts),
    )
    (r_start, r_end, step), _names, rows = dat
    ts = r_start
    res = {}
    for row in rows:
        v = row[0]
        if v is not None:
            res[ts] = v * 8.0  # octets/s -> bits/s
        ts += step
    return res


# ---------- iperf3 JSON parsing ----------
def _resample_records_to_dict(records, resample_sec=30) -> dict:
    """records: list[(epoch_seconds, bps)] -> resample (mean) to resample_sec."""
    if not records:
        return {}
    df = pd.DataFrame(records, columns=["timestamp", "bps"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
    df = df.set_index("timestamp").resample(f"{resample_sec}s").mean().dropna()
    return {int(ts.timestamp()): float(v) for ts, v in df["bps"].items()}


def parse_iperf_client_json(fname: str, resample_sec=30) -> dict:
    """Parse iperf3 CLIENT JSON (single JSON), convert relative seconds -> epoch, resample."""
    with open(fname, "r") as f:
        data = json.load(f)

    epoch_start = int(
        data.get("start", {}).get("timestamp", {}).get("timesecs", time.time())
    )

    records = []
    for it in data.get("intervals", []):
        s = it.get("sum", {})
        rel_start = s.get("start")  # seconds since start
        bps = s.get("bits_per_second")
        if rel_start is not None and bps is not None:
            abs_ts = epoch_start + float(rel_start)
            records.append((abs_ts, float(bps)))

    return _resample_records_to_dict(records, resample_sec)


def parse_iperf_server_json_blocks(fname: str, resample_sec=30) -> dict:
    """Parse iperf3 SERVER JSON which may contain multiple concatenated JSON blocks.
    Prefer 'server_output_json' if present in a block. Convert offsets -> epoch, resample.
    """
    with open(fname, "r") as f:
        raw = f.read().strip()

    # Split into balanced-JSON chunks by tracking braces
    blocks = raw.splitlines()
    json_chunks, buf, brace = [], "", 0
    for line in blocks:
        brace += line.count("{") - line.count("}")
        buf += line + "\n"
        if brace == 0 and buf.strip():
            json_chunks.append(buf.strip())
            buf = ""

    records = []
    for chunk in json_chunks:
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            continue

        if "server_output_json" in data:
            data = data["server_output_json"]

        epoch_start = int(
            data.get("start", {}).get("timestamp", {}).get("timesecs", time.time())
        )

        for it in data.get("intervals", []):
            s = it.get("sum", {})
            rel_start = s.get("start")
            bps = s.get("bits_per_second")
            if rel_start is not None and bps is not None:
                abs_ts = epoch_start + float(rel_start)
                records.append((abs_ts, float(bps)))

    if not records:
        logging.warning(f"No valid intervals parsed from {fname}")
    return _resample_records_to_dict(records, resample_sec)


# ---------- iperf3 runner ----------
def run_client(reverse: bool = False) -> None:
    flag = ["-R"] if reverse else []
    mode = "REVERSE" if reverse else "NORMAL"
    logging.info(f"Running iperf3 {mode} for {IPERF_DURATION}s...")
    cmd = [
        "iperf3", "-c", REMOTE_HOST,
        "-u", "-b", IPERF_BW,
        "-t", str(IPERF_DURATION),
        "-i", str(IPERF_RESOLUTION),
        "-J", "--get-server-output",
        *flag,
    ]
    with open(LOCAL_CLIENT_JSON, "w") as f:
        subprocess.run(cmd, stdout=f, check=True)
    logging.info(f"Client JSON saved: {LOCAL_CLIENT_JSON}")


# ---------- CSV writer ----------
def write_csv(rrd_in, rrd_out, in_series, out_series, overhead, out_csv):
    all_ts = set(rrd_in) | set(rrd_out) | set(in_series) | set(out_series)
    for m in overhead.values():
        all_ts |= set(m)
    rows = []
    for ts in sorted(all_ts):
        row = [
            ts,
            datetime.fromtimestamp(ts).isoformat(sep=' '),
            rrd_in.get(ts, ""),
            rrd_out.get(ts, ""),
            in_series.get(ts, ""),
            out_series.get(ts, "")
        ]
        # Append overhead metrics in fixed order
        for k in ["loadavg1", "memAvailReal", "SwapOut", "IORawSent"]:
            row.append(overhead.get(k, {}).get(ts, ""))
        rows.append(row)

    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "timestamp", "time",
            "rrd_in_bps", "rrd_out_bps",
            "iperf_server_in_bps", "iperf_server_out_bps",
            "cpu_load", "mem_avail", "swap_out", "io_sent"
        ])
        w.writerows(rows)
    logging.info(f"Wrote merged CSV {out_csv}")


# ---------- small helpers ----------
def series_time_range(series: dict):
    if not series:
        return None, None
    ts = sorted(series.keys())
    return ts[0], ts[-1]


# ---------- main flow ----------
def main():
    setup_logging()
    # Create data directory if it doesn't exist
    os.makedirs(JSON_DIR, exist_ok=True)

    # Pass 1: NORMAL (server receives -> inbound)
    pid = start_server()
    t_start = int(time.time())
    logging.info(f"raw t_start: {t_start} ({datetime.fromtimestamp(t_start).isoformat(sep=' ')})")

    sleep(3)  # give server a moment to start

    run_client(reverse=False)
    stop_server(pid)
    scp_server_json(osp.join(JSON_DIR, "iperf3_server_in.json"))

    # Pass 2: REVERSE (server sends -> outbound)
    pid = start_server()

    sleep(3)  # give server a moment to start

    run_client(reverse=True)
    stop_server(pid)
    scp_server_json(osp.join(JSON_DIR, "iperf3_server_out.json"))

    # --- WAIT and ALIGN to RRD_RESOLUTION ---
    logging.info("Waiting for OpenNMS/collectd to flush final RRD samples...")
    # conservative wait: 2 steps (adjust if your polling interval is larger)
    time.sleep(RRD_RESOLUTION * 2)

    t_end = int(time.time())
    logging.info(f"raw t_end: {t_end} ({datetime.fromtimestamp(t_end).isoformat(sep=' ')})")

    # align both start and end to the RRD grid
    t_start_aligned = align_down(t_start, RRD_RESOLUTION)
    t_end_aligned = align_up(t_end, RRD_RESOLUTION)

    logging.info(f"Aligned time window -> start: {t_start_aligned}, end: {t_end_aligned}, step: {RRD_RESOLUTION}s")

    # debug: print last update timestamps from RRD files
    last_in = get_rrd_last_update(RRD_IN)
    last_out = get_rrd_last_update(RRD_OUT)
    logging.info(f"RRD last update: IN={last_in} ({datetime.fromtimestamp(last_in).isoformat(sep=' ' ) if last_in else 'N/A'}) OUT={last_out} ({datetime.fromtimestamp(last_out).isoformat(sep=' ') if last_out else 'N/A'})")

    # Parse iperf results (server-side metrics only)
    logging.info("Parsing iperf3 inbound (server receive)")
    server_in_series = parse_iperf_server_json_blocks(osp.join(JSON_DIR, "iperf3_server_in.json"), RRD_RESOLUTION)
    logging.info("Parsing iperf3 outbound (server send)")
    server_out_series = parse_iperf_server_json_blocks(osp.join(JSON_DIR, "iperf3_server_out.json"), RRD_RESOLUTION)

    # Determine combined iperf time window: from start of IN phase to end of OUT phase
    in_min, in_max = series_time_range(server_in_series)
    out_min, out_max = series_time_range(server_out_series)

    # compute iperf overall min/max safely (handle empty series)
    candidates_min = [v for v in (in_min, out_min) if v is not None]
    candidates_max = [v for v in (in_max, out_max) if v is not None]

    if not candidates_min or not candidates_max:
        logging.warning("One or both iperf series are empty — cannot determine full iperf range reliably.")
        ip_min = ip_max = None
    else:
        ip_min = min(candidates_min)
        ip_max = max(candidates_max)

    logging.info(f"iperf combined range: {ip_min} -> {ip_max}")

    # Fetch RRD data using aligned window (already aligned earlier)
    logging.info("Fetching RRD...")
    rrd_in = fetch_rrd(RRD_IN, t_start_aligned, t_end_aligned, RRD_RESOLUTION)
    rrd_out = fetch_rrd(RRD_OUT, t_start_aligned, t_end_aligned, RRD_RESOLUTION)

    # Fetch overhead metrics from Core ===
    overhead_series = fetch_multiple_rrd(RRD_OVERHEAD, t_start_aligned, t_end_aligned, RRD_RESOLUTION)

    # debug: inspect overlap between iperf combined window and rrd
    rrd_min, rrd_max = series_time_range(rrd_in)
    
    logging.info(f"RRD range: {rrd_min} -> {rrd_max}")
    if ip_min is not None and ip_max is not None:
        overlap_start = max(rrd_min, ip_min) if rrd_min is not None else ip_min
        overlap_end   = min(rrd_max, ip_max) if rrd_max is not None else ip_max
        if overlap_start is not None and overlap_end is not None and overlap_start <= overlap_end:
            logging.info(f"Overlap exists: {overlap_start} -> {overlap_end}")
        else:
            logging.warning("No overlap between RRD and iperf series — consider increasing wait or checking polling interval")
    else:
        logging.warning("iperf combined range unknown, skip overlap check.")


    write_csv(rrd_in, rrd_out, server_in_series, server_out_series, CSV_OUT)
    logging.info("DONE ✅")


if __name__ == "__main__":
    main()
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path

# =========================
# Helper functions
# =========================
def safe_corr(a: pd.Series, b: pd.Series) -> float:
    s = pd.concat([a, b], axis=1).dropna()
    if len(s) < 2:
        return float("nan")
    return float(s.iloc[:, 0].corr(s.iloc[:, 1]))

def linreg_xy(x: pd.Series, y: pd.Series):
    s = pd.concat([x, y], axis=1).dropna()
    if len(s) < 2:
        return np.array([]), np.array([])
    xs = s.iloc[:, 0].values
    ys = s.iloc[:, 1].values
    coef = np.polyfit(xs, ys, 1)  # slope, intercept
    grid = np.linspace(np.nanmin(xs), np.nanmax(xs), 50)
    line = coef[0] * grid + coef[1]
    return grid, line

def calc_error(df, rrd_col, iperf_col):
    if iperf_col in df.columns:
        return np.where(
            (df[iperf_col].notna()) & (df[iperf_col] > 0),
            (df[rrd_col] - df[iperf_col]).abs() / df[iperf_col] * 100.0,
            np.nan
        )
    else:
        return np.nan

# =========================
# Load dữ liệu
# =========================
low  = pd.read_csv("data/low_load.csv")
high = pd.read_csv("data/high_load.csv")

for df in (low, high):
    # Chuyển cột thời gian về datetime
    df["time"] = pd.to_datetime(df["time"])
    # Tính toán lỗi phần trăm để so sánh độ chính xác thông lượng (OpenNMS vs iperf3) 
    df["error_in_%"]  = calc_error(df, "rrd_in_bps",  "iperf_server_in_bps")
    df["error_out_%"] = calc_error(df, "rrd_out_bps", "iperf_server_out_bps")

# =========================
# Tính toán tổng hợp
# =========================
corr_low_thr_cpu  = safe_corr(low["rrd_in_bps"],  low["cpu_load"])
corr_high_thr_cpu = safe_corr(high["rrd_in_bps"], high["cpu_load"])
corr_low_err_cpu  = safe_corr(low["error_in_%"],  low["cpu_load"])
corr_high_err_cpu = safe_corr(high["error_in_%"], high["cpu_load"])

summary = pd.DataFrame({
    "Scenario": ["Low Load", "High Load"],
    "Avg RRD In (bps)": [low["rrd_in_bps"].mean(),  high["rrd_in_bps"].mean()],
    "Avg iperf In (bps)": [low["iperf_server_in_bps"].mean(), high["iperf_server_in_bps"].mean()],
    "Mean Error In (%)": [low["error_in_%"].mean(), high["error_in_%"].mean()],
    "Avg RRD Out (bps)": [low["rrd_out_bps"].mean(), high["rrd_out_bps"].mean()],
    "Avg iperf Out (bps)": [
        low["iperf_server_out_bps"].mean()  if "iperf_server_out_bps"  in low.columns  else np.nan,
        high["iperf_server_out_bps"].mean() if "iperf_server_out_bps" in high.columns else np.nan
    ],
    "Mean Error Out (%)": [low["error_out_%"].mean(), high["error_out_%"].mean()],
    "Avg CPU (%)": [low["cpu_load"].mean(), high["cpu_load"].mean()],
    "Avg Mem Avail (MB)": [low["mem_avail"].mean(), high["mem_avail"].mean()],
    "Avg Swap Out": [low["swap_out"].mean(), high["swap_out"].mean()],
    "Avg IO Sent": [low["io_sent"].mean(), high["io_sent"].mean()],
    "Corr(Throughput–CPU)": [corr_low_thr_cpu, corr_high_thr_cpu],
    "Corr(Error–CPU)": [corr_low_err_cpu,  corr_high_err_cpu]
})

# =========================
# Biểu đồ Ingress Throughput (OpenNMS vs iperf3)
# =========================
fig_in = go.Figure()
fig_in.add_trace(go.Scatter(x=low["time"],  y=low["rrd_in_bps"],            name="RRD In – Low",  mode="lines"))
fig_in.add_trace(go.Scatter(x=low["time"],  y=low["iperf_server_in_bps"],   name="iperf In – Low",  mode="lines", line=dict(dash="dot")))
fig_in.add_trace(go.Scatter(x=high["time"], y=high["rrd_in_bps"],           name="RRD In – High", mode="lines"))
fig_in.add_trace(go.Scatter(x=high["time"], y=high["iperf_server_in_bps"],  name="iperf In – High", mode="lines", line=dict(dash="dot")))
fig_in.update_layout(
    title="Ingress Throughput: OpenNMS & iperf3",
    xaxis_title="Time",
    yaxis_title="Throughput (bps)",
    template="plotly_white",
    legend=dict(orientation="h", y=-0.2)
)

# =========================
# Biểu đồ Error Ingress (%)
# =========================
fig_err_in = go.Figure()
fig_err_in.add_trace(go.Scatter(x=low["time"],  y=low["error_in_%"],  name="Error In – Low",  mode="lines"))
fig_err_in.add_trace(go.Scatter(x=high["time"], y=high["error_in_%"], name="Error In – High", mode="lines"))
fig_err_in.update_layout(
    title="Measurement Error (%) – Ingress",
    xaxis_title="Time",
    yaxis_title="Error (%)",
    template="plotly_white",
    legend=dict(orientation="h", y=-0.2)
)

# =========================
# Biểu đồ Egress Throughput(OpenNMS vs iperf3)
# =========================
fig_out = go.Figure()
fig_out.add_trace(go.Scatter(x=low["time"],  y=low["rrd_out_bps"],              name="RRD Out – Low",  mode="lines"))
fig_out.add_trace(go.Scatter(x=low["time"],  y=low["iperf_server_out_bps"],     name="iperf Out – Low",  mode="lines", line=dict(dash="dot")))
fig_out.add_trace(go.Scatter(x=high["time"], y=high["rrd_out_bps"],             name="RRD Out – High", mode="lines"))
fig_out.add_trace(go.Scatter(x=high["time"], y=high["iperf_server_out_bps"],    name="iperf Out – High", mode="lines", line=dict(dash="dot")))
fig_out.update_layout(
    title="Egress Throughput: OpenNMS & iperf3",
    xaxis_title="Time",
    yaxis_title="Throughput (bps)",
    template="plotly_white",    
    legend=dict(orientation="h", y=-0.2)
)

# =========================
# Biểu đồ Error Egress (%)
# =========================
fig_err_out = go.Figure()
fig_err_out.add_trace(go.Scatter(x=low["time"],  y=low["error_out_%"],  name="Error Out – Low",  mode="lines"))
fig_err_out.add_trace(go.Scatter(x=high["time"], y=high["error_out_%"], name="Error Out – High", mode="lines"))
fig_err_out.update_layout(
    title="Measurement Error (%) – Egress",
    xaxis_title="Time",
    yaxis_title="Error (%)",
    template="plotly_white",
    legend=dict(orientation="h", y=-0.2)
)

# =========================
# CPU / Memory / Swap / Disk IO
# =========================
fig_cpu = go.Figure()
fig_cpu.add_trace(go.Scatter(x=low["time"],  y=low["cpu_load"],  name="CPU – Low",  mode="lines"))
fig_cpu.add_trace(go.Scatter(x=high["time"], y=high["cpu_load"], name="CPU – High", mode="lines"))
fig_cpu.update_layout(title="CPU Load (%)", xaxis_title="Time", yaxis_title="CPU %", template="plotly_white", legend=dict(orientation="h", y=-0.2))

fig_mem = go.Figure()
fig_mem.add_trace(go.Scatter(x=low["time"],  y=low["mem_avail"],  name="Mem – Low",  mode="lines"))
fig_mem.add_trace(go.Scatter(x=high["time"], y=high["mem_avail"], name="Mem – High", mode="lines"))
fig_mem.update_layout(title="Memory Available (MB)", xaxis_title="Time", yaxis_title="MB", template="plotly_white", legend=dict(orientation="h", y=-0.2))

fig_swap = go.Figure()
fig_swap.add_trace(go.Scatter(x=low["time"],  y=low["swap_out"],  name="Swap Out – Low",  mode="lines"))
fig_swap.add_trace(go.Scatter(x=high["time"], y=high["swap_out"], name="Swap Out – High", mode="lines"))
fig_swap.update_layout(title="Swap Out", xaxis_title="Time", yaxis_title="pages/s", template="plotly_white", legend=dict(orientation="h", y=-0.2))

fig_io = go.Figure()
fig_io.add_trace(go.Scatter(x=low["time"],  y=low["io_sent"],  name="IO Sent – Low",  mode="lines"))
fig_io.add_trace(go.Scatter(x=high["time"], y=high["io_sent"], name="IO Sent – High", mode="lines"))
fig_io.update_layout(title="Disk I/O Sent", xaxis_title="Time", yaxis_title="I/O units", template="plotly_white", legend=dict(orientation="h", y=-0.2))

# =========================
# Trade-off (Enhanced)
# =========================
def safe_corr(a, b):
    s = pd.concat([a, b], axis=1).dropna()
    return s.corr().iloc[0, 1] if len(s) >= 2 else np.nan

low_act  = low[(low["iperf_server_in_bps"]  > 0) & (low["error_in_%"].notna())  & (low["cpu_load"].notna())]
high_act = high[(high["iperf_server_in_bps"] > 0) & (high["error_in_%"].notna()) & (high["cpu_load"].notna())]

low_mean_err,  low_mean_cpu  = low_act["error_in_%"].mean(),  low_act["cpu_load"].mean()
high_mean_err, high_mean_cpu = high_act["error_in_%"].mean(), high_act["cpu_load"].mean()

r_low  = safe_corr(low_act["error_in_%"],  low_act["cpu_load"])
r_high = safe_corr(high_act["error_in_%"], high_act["cpu_load"])

x_low,  y_low  = linreg_xy(low_act["error_in_%"],  low_act["cpu_load"])
x_high, y_high = linreg_xy(high_act["error_in_%"], high_act["cpu_load"])

fig_tradeoff = go.Figure()

# Low load samples
fig_tradeoff.add_trace(go.Scatter(
    x=low_act["error_in_%"], 
    y=low_act["cpu_load"],
    mode="markers", 
    name=f"Low Load (r={r_low:.2f})",
    opacity=0.55,
    marker=dict(
        color="blue",
        size=np.clip(low_act["io_sent"]/low_act["io_sent"].max()*15, 5, 15),
        sizemode="area",
        sizeref=2.*max(low_act["io_sent"])/15**2,
        line=dict(width=0.3, color="darkblue"),
        symbol="circle"
    ),
    hovertemplate="Error In: %{x:.2f}%<br>CPU: %{y:.2f}%<br>I/O Sent: %{marker.size:.1f}"
))

# High load samples
fig_tradeoff.add_trace(go.Scatter(
    x=high_act["error_in_%"], 
    y=high_act["cpu_load"],
    mode="markers", 
    name=f"High Load (r={r_high:.2f})",
    opacity=0.55,
    marker=dict(
        color="red",
        size=np.clip(high_act["io_sent"]/high_act["io_sent"].max()*15, 5, 15),
        sizemode="area",
        sizeref=2.*max(high_act["io_sent"])/15**2,
        line=dict(width=0.3, color="darkred"),
        symbol="circle"
    ),
    hovertemplate="Error In: %{x:.2f}%<br>CPU: %{y:.2f}%<br>I/O Sent: %{marker.size:.1f}"
))

# Regression lines
if len(x_low):
    fig_tradeoff.add_trace(go.Scatter(
        x=x_low, y=y_low, 
        mode="lines", 
        name="Low trend", 
        line=dict(color="blue", width=2, dash="dot")
    ))
if len(x_high):
    fig_tradeoff.add_trace(go.Scatter(
        x=x_high, y=y_high, 
        mode="lines", 
        name="High trend", 
        line=dict(color="red", width=2, dash="dot")
    ))

# Mean points
fig_tradeoff.add_trace(go.Scatter(
    x=[low_mean_err], y=[low_mean_cpu],
    mode="markers+text", 
    name="Low Mean",
    text=[f"μ({low_mean_err:.1f}%, {low_mean_cpu:.1f}%)"],
    textposition="top center",
    marker=dict(size=14, symbol="diamond", color="blue", line=dict(width=1, color="black"))
))
fig_tradeoff.add_trace(go.Scatter(
    x=[high_mean_err], y=[high_mean_cpu],
    mode="markers+text", 
    name="High Mean",
    text=[f"μ({high_mean_err:.1f}%, {high_mean_cpu:.1f}%)"],
    textposition="top center",
    marker=dict(size=14, symbol="diamond", color="red", line=dict(width=1, color="black"))
))

fig_tradeoff.update_layout(
    title=(
        "Trade-off: Measurement Error vs CPU Load<br>"
        "<sup>Correlation (r) and Disk I/O indicated by marker size</sup>"
    ),
    xaxis_title="Measurement Error In (%)",
    yaxis_title="CPU Load (%)",
    template="plotly_white",
    legend=dict(orientation="h", y=-0.25),
    margin=dict(t=90, b=70, l=60, r=30),
    height=550
)

fig_tradeoff.show()
# =========================
# Xuất HTML (nhúng Plotly JS 1 lần)
# =========================
html_header = """
<html>
<head>
<meta charset="utf-8">
<title>OpenNMS Accuracy & Resource Trade-off</title>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #fafafa; margin: 0; }
  .container { max-width: 1200px; margin: 0 auto; padding: 36px 28px 60px; }
  h1 { text-align: center; color: #222; margin-bottom: 8px; }
  h2 { color: #333; border-bottom: 2px solid #e5e5e5; padding-bottom: 6px; margin-top: 34px; }
  p.lead { text-align: center; color: #666; margin-top: 0; }
  table { border-collapse: collapse; width: 100%; font-size: 14px; }
  th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
  th { background: #f7f7f7; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }
</style>
</head>
<body>
<div class="container">
  <h1>OpenNMS Throughput–Resource Accuracy Trade-off Analysis</h1>
  <p class="lead"><em>Đánh giá độ chính xác và chi phí tài nguyên của OpenNMS Core ở hai mức tải để phân tích trade-off giữa độ chính xác và tần suất thu thập dữ liệu.</em></p>
"""

html_footer = """
</div>
</body>
</html>
"""

summary_html = summary.to_html(index=False, float_format="%.2f")

body_parts = [
    "<h2>Tổng hợp chỉ số (Summary)</h2>",
    summary_html,
    "<h2>Độ chính xác Throughput</h2>",
    "<div class='grid-2'>",
    fig_in.to_html(full_html=False, include_plotlyjs='cdn'), # Nhúng Plotly JS bằng tag 'cdn' một lần
    fig_out.to_html(full_html=False, include_plotlyjs=False),
    "</div>",
    "<div class='grid-2'>",
    fig_err_in.to_html(full_html=False, include_plotlyjs=False),
    fig_err_out.to_html(full_html=False, include_plotlyjs=False),
    "</div>",
    "<h2>Chi phí tài nguyên hệ thống</h2>",
    "<div class='grid-2'>",
    fig_cpu.to_html(full_html=False, include_plotlyjs=False),
    fig_mem.to_html(full_html=False, include_plotlyjs=False),
    "</div>",
    "<div class='grid-2'>",
    fig_swap.to_html(full_html=False, include_plotlyjs=False),
    fig_io.to_html(full_html=False, include_plotlyjs=False),
    "</div>",
    "<h2>Trade-off: Error (%) vs CPU (%)</h2>",
    fig_tradeoff.to_html(full_html=False, include_plotlyjs=False)
]

html = html_header + "\n".join(body_parts) + html_footer
Path("OpenNMS_Iperf_Comparison_Report.html").write_text(html, encoding="utf-8")

print("✅ Đã tạo: OpenNMS_Iperf_Comparison_Report.html")

#!/bin/bash

# Script to SYNC local files to a remote machine and run the script.
# Ideal for testing local changes without committing/pushing to Git.

# --- Configuration ---
REMOTE_USER="tung196"
REMOTE_HOST="100.97.19.21"       # Tailscale IP for Thinkpad X260
SSH_KEY_PATH=~/.ssh/id_ed25519   # Path to your private SSH key (avoid quotes so ~ expands)

REPO_NAME="opennms-data-fetcher"
REMOTE_REPO_DIR="/home/${REMOTE_USER}/${REPO_NAME}"

# --- Ensure remote directory exists ---
# This is important for the first time rsync runs.
echo "Ensuring remote directory ${REMOTE_REPO_DIR} exists..."
ssh -i "${SSH_KEY_PATH}" "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p ${REMOTE_REPO_DIR}"

# --- rsync ---
echo "Syncing local files to ${REMOTE_HOST}..."
rsync -avz --delete \
    --exclude='.git' \
    --exclude='.gitignore' \
    --exclude='*.sh' \
    --exclude='*.log' \
    --exclude='json_data/' \
    --exclude='__pycache__/' \
    --exclude='merged_bits_dual-KB02.csv' \
    --exclude='merged_bits_dual.csv' \
    -e "ssh -i ${SSH_KEY_PATH}" \
    . "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_REPO_DIR}/"

if [ $? -ne 0 ]; then
    echo "rsync failed. Aborting."
    exit 1
fi
echo "Sync complete."

# --- SSH and Execute ---
echo "Running Python script on remote..."

ssh -i "${SSH_KEY_PATH}" "${REMOTE_USER}@${REMOTE_HOST}" bash <<EOF
set -e

cd "${REMOTE_REPO_DIR}"

# Define the log file name (CHANGE THIS to your actual log file name!)
LOG_FILE="data_fetcher.log"

# Run the Python script in the background
# Use 'nohup' if you want it to survive SSH session disconnection (optional)
python3 main.py >/dev/null 2>&1 &
PYTHON_PID=\$! # Get the Process ID (PID) of the Python script

rm -f "\${LOG_FILE}" # Remove old log file if exists

echo "--- Remote execution started. Following log file: \${LOG_FILE} ---"

sleep 2 # Give it a moment to start and create the log file

# Start following the log file in the background
tail -f "\${LOG_FILE}" &
TAIL_PID=\$! # Get the PID of the tail process

# Wait for the Python process to finish
wait \$PYTHON_PID

# Once Python is done, stop the tail process
kill \$TAIL_PID 2>/dev/null

echo "--- Remote execution finished ---"
EOF

# Copy the csv file back to local machine
echo "Copying result CSV file back to local machine..."
scp -i "${SSH_KEY_PATH}" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_REPO_DIR}/merged_bits_dual.csv" .

# Copy the log file back to local machine
echo "Copying log file back to local machine..."
scp -i "${SSH_KEY_PATH}" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_REPO_DIR}/data_fetcher.log" .

# --- Post Execution ---
if [ $? -eq 0 ]; then
    echo "Script executed successfully on remote."
else
    echo "An error occurred during remote execution."
fi

echo "Sync and run script finished."

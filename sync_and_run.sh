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
set -e  # Exit immediately if a command exits with a non-zero status.
set -x  # Print commands and their arguments as they are executed.

cd "${REMOTE_REPO_DIR}"
python3 main.py

echo "--- Remote execution finished ---"
EOF

# --- Post Execution ---
if [ $? -eq 0 ]; then
    echo "Script executed successfully on remote."
else
    echo "An error occurred during remote execution."
fi

echo "Sync and run script finished."

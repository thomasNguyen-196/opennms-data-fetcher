#!/bin/bash

# Script to deploy and run the opennms-data-fetcher on a remote machine.

# --- Configuration ---
REMOTE_USER="tung196"
REMOTE_HOST="100.71.60.159"      # IP for Thinkpad X260
REMOTE_DIR="/home/tung196/collect-data-opennms" # Project directory on remote
SSH_KEY_PATH="~/.ssh/id_ed25519" # Path to your private SSH key

# --- SSH and Execute ---
echo "Connecting to ${REMOTE_HOST} using key ${SSH_KEY_PATH}..."

ssh -i "${SSH_KEY_PATH}" "${REMOTE_USER}@${REMOTE_HOST}" "echo 'Executing on remote:'; set -x; cd ${REMOTE_DIR} && git pull && python3 main.py"

if [ $? -eq 0 ]; then
    echo "Script executed successfully on remote."
else
    echo "An error occurred during remote execution."
fi

echo "Deployment script finished."
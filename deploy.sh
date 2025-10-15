#!/bin/bash

# Script to deploy and run the opennms-data-fetcher on a remote machine.
# It checks if the repo exists, clones or pulls, then runs the script.

# --- Configuration ---
REMOTE_USER="tung196"
REMOTE_HOST="100.97.19.21"       # Tailscale IP for Thinkpad X260
SSH_KEY_PATH=~/.ssh/id_ed25519   # Path to your private SSH key (avoid quotes so ~ expands)

REPO_URL="https://github.com/thomasNguyen-196/opennms-data-fetcher.git"
REPO_NAME="opennms-data-fetcher"
REMOTE_REPO_DIR="/home/${REMOTE_USER}/${REPO_NAME}"

# --- SSH and Execute ---
echo "Connecting to ${REMOTE_HOST}..."

# Use heredoc to send multi-line command safely to the remote host.
# NOTE: Unquoted EOF so that local variables are expanded before sending to remote.
ssh -i "${SSH_KEY_PATH}" "${REMOTE_USER}@${REMOTE_HOST}" bash <<EOF
set -e  # Exit immediately if a command exits with a non-zero status.
set -x  # Print commands and their arguments as they are executed.

echo '--- Starting deployment on remote ---'

# Ensure parent directory exists
mkdir -p "$(dirname "${REMOTE_REPO_DIR}")"

# Check if the directory exists and clone or pull accordingly
if [ -d "${REMOTE_REPO_DIR}" ]; then
  echo 'Repository directory found. Pulling latest changes...'
  cd "${REMOTE_REPO_DIR}"
  git fetch origin
  git checkout main
  git pull --ff-only origin main
else
  echo 'Repository directory not found. Cloning from ${REPO_URL}...'
  git clone "${REPO_URL}" "${REMOTE_REPO_DIR}"
  cd "${REMOTE_REPO_DIR}"
fi

# By this point, we are guaranteed to be in the correct directory.
echo '--- Running Python script ---'
python3 main.py

echo '--- Remote execution finished ---'
EOF

# --- Post Execution ---
if [ \$? -eq 0 ]; then
    echo "Deployment script executed successfully on remote."
else
    echo "An error occurred during remote execution."
fi

echo "Deployment script finished."

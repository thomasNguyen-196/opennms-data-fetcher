#!/bin/bash

# Script to deploy and run the opennms-data-fetcher on a remote machine.
# It checks if the repo exists, clones or pulls, then runs the script.

# --- Configuration ---
REMOTE_USER="tung196"
REMOTE_HOST="100.97.19.21"      # Tailscale IP for Thinkpad X260
SSH_KEY_PATH="~/.ssh/id_ed25519" # Path to your private SSH key

REPO_URL="https://github.com/thomasNguyen-196/opennms-data-fetcher.git"
REPO_NAME="opennms-data-fetcher"
REMOTE_REPO_DIR="/home/tung196/${REPO_NAME}"

# --- SSH and Execute ---
echo "Connecting to ${REMOTE_HOST}..."

# The multi-line command to be executed on the remote server.
REMOTE_COMMAND="
set -e # Exit immediately if a command exits with a non-zero status.
set -x # Print commands and their arguments as they are executed.

echo '--- Starting deployment on remote ---'

# Check if the directory exists and clone or pull accordingly
if [ -d \"${REMOTE_REPO_DIR}\" ]; then
  echo 'Repository directory found. Pulling latest changes...'
  cd \"${REMOTE_REPO_DIR}\" 
  git pull origin main
else
  echo 'Repository directory not found. Cloning from ${REPO_URL}...'
  git clone \"${REPO_URL}\" \"${REMOTE_REPO_DIR}\" 
  cd \"${REMOTE_REPO_DIR}\" 
fi

# By this point, we are guaranteed to be in the correct directory.
echo '--- Running Python script ---
python3 main.py

echo '--- Remote execution finished ---
"

ssh -i "${SSH_KEY_PATH}" "${REMOTE_USER}@${REMOTE_HOST}" "${REMOTE_COMMAND}"

if [ $? -eq 0 ]; then
    echo "Deployment script executed successfully on remote."
else
    echo "An error occurred during remote execution."
fi

echo "Deployment script finished."
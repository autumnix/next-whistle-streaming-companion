#!/usr/bin/env bash
set -euo pipefail

# Change to the script's own directory
cd "$(dirname "$0")"

# Activate the virtual environment
source .venv/bin/activate

# Config file (default: config.yaml in this directory)
CONFIG="${NWSC_CONFIG:-config.yaml}"

if [ ! -f "$CONFIG" ]; then
    echo "Config file not found: $CONFIG"
    echo "Copy config.example.yaml to config.yaml and edit it with your settings."
    echo ""
    echo "  cp config.example.yaml config.yaml"
    echo ""
    exit 1
fi

echo "Config:  $CONFIG"
echo "Launching Next Whistle Streaming Companion..."
echo ""

python -m nwsc --config "$CONFIG"

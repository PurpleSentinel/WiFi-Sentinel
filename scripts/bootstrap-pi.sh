#!/usr/bin/env bash
set -euo pipefail
# Run from repository root on Pi OS. Not intended to run as root.
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip
python3 -m venv collector/.venv
collector/.venv/bin/python -m pip install -e './collector'
echo 'Collector ready. See docs/RASPBERRY_PI.md for USB and service setup.'

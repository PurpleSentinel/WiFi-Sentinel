#!/usr/bin/env bash
set -euo pipefail
# Run from repository root. ESP-IDF is installed separately; see docs.
sudo dnf install -y python3 python3-pip python3-virtualenv
python3 -m venv collector/.venv
collector/.venv/bin/python -m pip install -e './collector[dev]'
collector/.venv/bin/python -m pytest -q collector/tests
echo 'Python collector ready. See docs/FEDORA_SETUP.md to build firmware.'

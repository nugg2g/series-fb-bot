#!/bin/bash
# start.sh - Launcher for Facebook Reels Auto Bot 2 on Dell Server
VENV_PYTHON="/home/moes/venv/bin/python3"
SCRIPT_DIR="/home/moes/storage/Projects/Page Reel uplaod 2"
LOGS_DIR="/home/moes/storage/logs"
mkdir -p "$LOGS_DIR"

cd "$SCRIPT_DIR"
exec "$VENV_PYTHON" "$SCRIPT_DIR/cli.py" --start >> "$LOGS_DIR/page_reel_upload_2.log" 2>&1

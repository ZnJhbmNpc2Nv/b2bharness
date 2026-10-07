#!/usr/bin/env bash
echo "========================================================="
echo "Starting Corporate Spec-Kit on localhost:8470..."
echo "Zero uv, zero venv, zero pip required."
echo "========================================================="
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
python3 "$DIR/run_speckit.py" "$@"

#!/bin/bash
set -e

# Get directory of this script
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Set working directory
cd "$BASE_DIR"

echo "Working directory set to: $BASE_DIR"

# Activate virtual environment
echo "Activating virtual environment..."
source "$BASE_DIR/venv/bin/activate"

# Start Gunicorn
exec python -m gunicorn \
    --workers 4 \
    --threads 2 \
    --worker-class gthread \
    --timeout 120 \
    --graceful-timeout 120 \
    --keep-alive 5 \
    --bind 0.0.0.0:8040 \
    --log-level debug \
    --capture-output \
    --access-logfile "$BASE_DIR/gunicorn_access.log" \
    --error-logfile "$BASE_DIR/gunicorn_error.log" \
    wsgi:server


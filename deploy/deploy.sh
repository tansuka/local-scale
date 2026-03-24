#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Pulling latest changes..."
git -C "$ROOT_DIR" pull

echo "Building frontend..."
cd "$ROOT_DIR/frontend"
npm run build

echo "Installing backend..."
cd "$ROOT_DIR/backend"
if [[ -x ".venv/bin/pip" ]]; then
  .venv/bin/pip install -e .
else
  pip install -e .
fi

echo "Restarting local-scale service..."
sudo systemctl restart local-scale

echo "Deploy complete."

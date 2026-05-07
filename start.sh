#!/usr/bin/bash
# VizR Startup Script with Mode Selection
# Supports both development and production modes

set -e

# Ensure PATH includes common directories
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/venvs/vizr/bin:$PATH

# Read MODE from environment variable (default: production)
MODE=${MODE:-production}

echo "========================================"
echo "  VizR Startup Script"
echo "  Mode: $MODE"
echo "  VIZR_PATH (container): ${VIZR_PATH:-/vizr}"
echo "  VIZR_PATH (host): ${HOST_VIZR_PATH:-unknown}"
echo "  Docker API Version: ${DOCKER_API_VERSION:-auto}"
echo "========================================"

# Redis 시작
echo "[1/5] Starting Redis..."
redis-server --daemonize yes --maxmemory 256mb --maxmemory-policy allkeys-lru

# Install frontend dependencies
echo "[2/5] Checking frontend dependencies..."
if [ ! -f '/app/frontend/node_modules/.bin/vite' ] || [ '/app/frontend/package.json' -nt '/app/frontend/node_modules' ]; then
  echo "Installing frontend dependencies..."
  cd /app/frontend && npm install
else
  echo "Frontend dependencies already installed"
fi

# Mode-specific startup
if [ "$MODE" = "production" ]; then
  echo "[3/5] Production mode: Using pre-built frontend..."
  echo "Frontend already built in Docker image"

  echo "[4/5] Starting Flask backend (serves built frontend)..."
  echo "Access VizR at: http://localhost:5001"
  cd /app && PYTHONPATH=/app USE_REDIS=true REDIS_HOST=localhost /opt/venvs/vizr/bin/python3 backend/app.py

else
  echo "[3/5] Development mode: Starting Vite dev server..."
  cd /app/frontend && npm run dev &

  echo "[4/5] Starting Flask backend..."
  echo "Access VizR at: http://localhost:5173 (Frontend)"
  echo "Backend API at: http://localhost:5001"
  cd /app && PYTHONPATH=/app USE_REDIS=true REDIS_HOST=localhost /opt/venvs/vizr/bin/python3 backend/app.py
fi
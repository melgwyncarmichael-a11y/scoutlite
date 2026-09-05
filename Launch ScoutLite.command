#!/bin/zsh
# Double-clickable launcher for ScoutLite
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "First run — creating virtual environment…"
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

# If an instance is already healthy on 8510, just open it instead of failing
# with "Port 8510 is not available".
if curl -s -m 2 http://localhost:8510/_stcore/health | grep -q ok; then
  echo "ScoutLite is already running — opening it…"
  open http://localhost:8510
  exit 0
fi

# Port held by a stale/dead process: clear it so the fresh start succeeds.
if lsof -nP -iTCP:8510 -sTCP:LISTEN > /dev/null 2>&1; then
  echo "Clearing stale process on port 8510…"
  lsof -nP -iTCP:8510 -sTCP:LISTEN -t | xargs kill 2>/dev/null
  sleep 2
fi

echo "Starting ScoutLite…"
.venv/bin/streamlit run app.py --server.port 8510

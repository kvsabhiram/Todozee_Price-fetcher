#!/usr/bin/env bash
# Deploy/refresh the Todozee Price Fetcher. Invoked at boot (initial install)
# and by CI/CD via SSM RunCommand: sudo /usr/local/bin/deploy-app.sh <git-sha>
set -euo pipefail

APP_DIR=/opt/todozee-price
APP_USER=todozee
APP_PORT=5006
SHA="${1:-}"

echo "[deploy] target sha='${SHA:-<latest main>}'"

cd "$APP_DIR"

# Fetch latest and move to the requested commit (or tip of main).
git config --system --add safe.directory "$APP_DIR" || true
sudo -u "$APP_USER" git fetch --all --prune
if [ -n "$SHA" ]; then
  sudo -u "$APP_USER" git checkout -f "$SHA"
else
  sudo -u "$APP_USER" git checkout -f main
  sudo -u "$APP_USER" git pull --ff-only origin main
fi

# Sync dependencies.
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

# Restart the service.
systemctl restart todozee-price

# Health gate: wait for the API to answer.
echo "[deploy] waiting for health on :$APP_PORT …"
for i in $(seq 1 20); do
  sleep 3
  if curl -fsS "http://127.0.0.1:${APP_PORT}/api/health" >/dev/null 2>&1; then
    echo "[deploy] OK — /api/health responding"
    curl -fsS "http://127.0.0.1:${APP_PORT}/api/health" || true
    echo
    exit 0
  fi
done

echo "[deploy] FAILED — health check did not pass; recent logs:"
journalctl -u todozee-price --no-pager -n 50 || true
tail -n 50 /var/log/todozee-price/app.log 2>/dev/null || true
exit 1

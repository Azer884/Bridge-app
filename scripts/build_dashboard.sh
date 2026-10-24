#!/usr/bin/env bash
# Rebuilds the hosted dashboard (the web app from the frontend branch) into ./dashboard, which the server serves.
# Run from the repo root with the frontend folder checked out, e.g.:
#   git worktree add ../Bridge-app-frontend origin/feature/frontend
#   scripts/build_dashboard.sh ../Bridge-app-frontend/frontend/web
# then commit ./dashboard and republish.
set -euo pipefail
web="${1:?usage: scripts/build_dashboard.sh <path to frontend/web>}"
root="$(cd "$(dirname "$0")/.." && pwd)"
(
  cd "$web"
  npm install --no-audit --no-fund
  VITE_USE_MOCK=false VITE_BOOKINGS_LIVE=true npm run build
)
rm -rf "$root/dashboard"
mkdir -p "$root/dashboard"
cp -r "$web/dist/." "$root/dashboard/"
echo "Dashboard built into $root/dashboard"

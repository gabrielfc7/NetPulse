#!/usr/bin/env bash
# ==============================================================================
# NetPulse Sentry Fleet - Autonomous GitHub Auto-Updater
# Checks upstream GitHub for new commits, pulls changes, and restarts containers.
# ==============================================================================
set -euo pipefail

REPO_DIR="/home/gabriel/NetPulse"
LOG_TAG="[NetPulse-AutoUpdater]"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG $1"
}

if [ ! -d "$REPO_DIR/.git" ]; then
    log "Error: $REPO_DIR is not a git repository."
    exit 1
fi

cd "$REPO_DIR"

# Ensure non-interactive git
export GIT_TERMINAL_PROMPT=0

log "Checking GitHub origin/main for updates..."
git fetch origin main --quiet || {
    log "Warning: git fetch failed (offline or GitHub unreachable). Skipping."
    exit 0
}

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    log "Up to date with GitHub (${LOCAL:0:7}). No changes needed."
    exit 0
fi

log "Update detected! Local: ${LOCAL:0:7} -> Remote: ${REMOTE:0:7}"
CHANGED_FILES=$(git diff --name-only "$LOCAL" "$REMOTE")

log "Safely pulling latest changes from GitHub..."
# Discard local modifications to tracked files to ensure clean fast-forward
git reset --hard "$LOCAL" --quiet
git pull --ff-only origin main

NEW_HEAD=$(git rev-parse HEAD)
log "Successfully updated repository to commit ${NEW_HEAD:0:7}"

# Determine which containers need reloading
if echo "$CHANGED_FILES" | grep -qE "(Dockerfile|requirements.txt|backend/|frontend/|docker-compose.yml|run.py)"; then
    log "Application code changed. Rebuilding and recreating NetPulse container..."
    docker compose up -d --build netpulse
fi

if echo "$CHANGED_FILES" | grep -qE "(portal/)"; then
    log "Portal gateway files changed. Reloading pi-portal..."
    docker restart pi-portal || true
fi

if echo "$CHANGED_FILES" | grep -qE "(homepage/)"; then
    log "Homepage dashboard configuration changed. Reloading homepage..."
    docker restart homepage || true
fi

log "Fleet update sequence completed successfully!"

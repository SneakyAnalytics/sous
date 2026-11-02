#!/bin/bash
# Sourced by deploy_to_beelink.sh. Machine-specific values live in deploy.local.env (git-ignored).
_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_ENV="${DEPLOY_LOCAL_ENV:-$_root/deploy.local.env}"
if [[ ! -f "$LOCAL_ENV" ]]; then
  echo "❌ $LOCAL_ENV not found. Copy deploy.local.env.example to deploy.local.env and fill it in."
  exit 1
fi
set -a; source "$LOCAL_ENV"; set +a
: "${BEELINK_HOST:?set BEELINK_HOST in deploy.local.env}"
: "${BEELINK_USER:?set BEELINK_USER in deploy.local.env}"
: "${BEELINK_HOME:?set BEELINK_HOME in deploy.local.env}"
BEELINK="${BEELINK_USER}@${BEELINK_HOST}"
BEELINK_HOME_BS="${BEELINK_HOME//\//\\}"
REMOTE_DIR_FWD="${BEELINK_HOME}/sous"
REMOTE_DIR="${BEELINK_HOME_BS}\\sous"

#!/bin/bash
# Deploy Sous to the Beelink by pulling prebuilt images (built by GitHub Actions from main).
# Same pattern as fitness_tracker: the Beelink builds nothing, and every deploy is pinned to a commit.
#
# Usage:
#   ./deploy_to_beelink.sh                          # deploy the commit origin/main points at
#   ./deploy_to_beelink.sh --env ANTHROPIC_API_KEY  # ...and copy just these keys from your Mac .env
#   ./deploy_to_beelink.sh --version <sha>          # deploy (or roll back to) a specific commit
set -euo pipefail

ENV_KEYS=(); VERSION=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV_KEYS+=("$2"); shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
done

cd "$(dirname "$0")"
source scripts/load_local_config.sh
remote() { ssh -o ConnectTimeout=10 "$BEELINK" "$@"; }
# Docker Desktop's Windows credential store fails over SSH; use a config that answers "none stored" (public images only).
DOCKER_SSH="set PATH=${BEELINK_HOME_BS}\.docker-ssh\bin;%PATH%&& set DOCKER_CONFIG=${BEELINK_HOME_BS}\.docker-ssh&&"
setup_docker_ssh() {
  remote "if not exist ${BEELINK_HOME_BS}\.docker-ssh\bin mkdir ${BEELINK_HOME_BS}\.docker-ssh\bin" >/dev/null
  scp -q scripts/deploy/docker-ssh/config.json "$BEELINK:${BEELINK_HOME}/.docker-ssh/config.json"
  scp -q scripts/deploy/docker-ssh/docker-credential-anon.cmd "$BEELINK:${BEELINK_HOME}/.docker-ssh/bin/docker-credential-anon.cmd"
}

echo "🔌 Checking the Beelink..."
remote "docker info --format {{.ServerVersion}}" >/dev/null || { echo "❌ Docker isn't responding on the Beelink."; exit 1; }
remote "if not exist $REMOTE_DIR mkdir $REMOTE_DIR" >/dev/null

if [[ -z "$VERSION" ]]; then
  git fetch -q origin main
  VERSION=$(git rev-parse origin/main)
fi
echo "📌 Deploying commit ${VERSION:0:12}  ($(git log -1 --format=%s "$VERSION" 2>/dev/null || echo 'unknown locally'))"

setup_docker_ssh
echo "🔎 Checking the images exist for that commit..."
for image in sous-api sous-web; do
  remote "$DOCKER_SSH docker manifest inspect ghcr.io/sneakyanalytics/$image:$VERSION" >/dev/null 2>&1 || {
    echo "❌ ghcr.io/sneakyanalytics/$image:$VERSION not found. Has the 'Build images' action finished, and are the packages public?"
    exit 1
  }
done

# Back up the live database (skipped on the very first deploy, when no container exists yet).
if remote "docker inspect sous-api" >/dev/null 2>&1; then
  echo "💾 Backing up the live database..."
  scp -q scripts/deploy/backup_db.py "$BEELINK:${BEELINK_HOME}/sous_backup_db.py"
  remote "docker cp ${BEELINK_HOME}/sous_backup_db.py sous-api:/tmp/backup_db.py" \
    && remote "docker exec sous-api python3 /tmp/backup_db.py" \
    || { echo "❌ Backup failed; not deploying."; exit 1; }
fi

merge_env() {
  local updates; updates=$(mktemp); cat > "$updates"
  scp -q scripts/deploy/merge_env.ps1 "$BEELINK:${BEELINK_HOME}/sous_merge_env.ps1"
  scp -q "$updates" "$BEELINK:${BEELINK_HOME}/sous_env_updates.txt"; rm -f "$updates"
  remote "powershell -NoProfile -ExecutionPolicy Bypass -File ${BEELINK_HOME}/sous_merge_env.ps1 -EnvFile $REMOTE_DIR_FWD/.env -Updates ${BEELINK_HOME}/sous_env_updates.txt"
}

echo "📤 Sending compose file..."
scp -q docker-compose.yml "$BEELINK:$REMOTE_DIR_FWD/docker-compose.yml"
if [[ ${#ENV_KEYS[@]} -gt 0 ]]; then
  for key in "${ENV_KEYS[@]}"; do grep -q "^$key=" .env || { echo "❌ $key not found in local .env"; exit 1; }; done
  for key in "${ENV_KEYS[@]}"; do
    line=$(grep "^$key=" .env); val=${line#*=}
    if [[ "$val" == *'$'* && "$val" != \'*\' ]]; then line="$key='$val'"; fi
    printf '%s\n' "$line"
  done | merge_env
fi
# The compose file mounts this path even when the calendar is off, so make sure a placeholder file exists.
remote "if not exist $REMOTE_DIR\\google_token.pickle type nul > $REMOTE_DIR\\google_token.pickle" >/dev/null
{
  echo "APP_VERSION=$VERSION"
  echo "SOUS_URL=http://${BEELINK_HOST}:3100"
  if [[ -n "${GOOGLE_TOKEN_FILE_ON_BEELINK:-}" ]]; then
    echo "GOOGLE_TOKEN_FILE=$GOOGLE_TOKEN_FILE_ON_BEELINK"
    echo "GOOGLE_TOKEN_PATH=/run/google/token.pickle"
  fi
} | merge_env

remote "docker volume inspect sous_sous_data >nul 2>&1 || docker volume create sous_sous_data" >/dev/null

echo "⬇️  Pulling images and restarting..."
remote "$DOCKER_SSH cd /d $REMOTE_DIR && docker compose pull && docker compose up -d --remove-orphans"

echo "🩺 Waiting for health..."
for i in $(seq 1 30); do
  if health=$(remote "curl -sf http://localhost:8100/health" 2>/dev/null); then echo "✅ $health"; break; fi
  sleep 10
  [[ $i -eq 30 ]] && { echo "❌ API not healthy. Logs: ssh $BEELINK \"docker logs --tail 80 sous-api\""; exit 1; }
done
remote "docker ps --format \"{{.Names}}\t{{.Status}}\""
remote "docker image prune -f" >/dev/null
echo; echo "Deployed ${VERSION:0:12}.  App: http://${BEELINK_HOST}:3100"

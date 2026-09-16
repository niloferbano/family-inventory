#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
release_sha=${1:?Release SHA required}
[[ "$release_sha" =~ ^[0-9a-f]{40}$ ]]
base=/home/nilofer/family-inventory
cd "$base/releases/$release_sha"
# Server credentials stay outside release archives.
ln -sfn "$base/.env" .env
ln -sfn "$base/.env.docker" .env.docker
export IMAGE_TAG="$release_sha"
compose=(docker compose --env-file .env -p family-inventory -f deploy/docker-compose.prod.yml)
trap 'rc=$?; if (( rc != 0 )); then "${compose[@]}" ps -a || true; echo "Deployment failed; previous release pointer preserved. Inspect server logs before retrying." >&2; fi' EXIT
"${compose[@]}" config --quiet
# Private images require a read-only GHCR login configured on this server.
"${compose[@]}" pull
"${compose[@]}" up -d --wait --wait-timeout 180 postgres rabbitmq redis
mkdir -p "$base/backups"
backup="$base/backups/pre-$release_sha-$(date -u +%Y%m%dT%H%M%SZ).dump"
"${compose[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' > "$backup"
test -s "$backup"
"${compose[@]}" exec -T postgres pg_restore --list < "$backup" > /dev/null
# Compose runs migrate once; application services wait for its successful exit.
"${compose[@]}" up -d --no-build --wait --wait-timeout 180
# Confirm the public proxy returns API JSON, not the SPA's fallback HTML.
healthy=false
for attempt in {1..12}; do
  if curl --silent --show-error --fail --max-time 10 https://inventory.nilofer.com/health \
      | python3 -c 'import json,sys; assert json.load(sys.stdin).get("status") == "ok"'; then
    healthy=true
    break
  fi
  sleep 5
done
[[ "$healthy" == true ]]
curl --silent --show-error --fail --max-time 20 https://inventory.nilofer.com/ > /dev/null
"${compose[@]}" ps -a
# Persist the successful tag for subsequent manual Compose commands.
python3 - "$base/.env" "$release_sha" <<'PY'
import os
import sys
from pathlib import Path
path = Path(sys.argv[1])
lines = [line for line in path.read_text().splitlines() if not line.strip().startswith(('IMAGE_TAG=', 'export IMAGE_TAG='))]
lines.append(f'IMAGE_TAG={sys.argv[2]}')
tmp = path.with_name('.env.release-tmp')
tmp.write_text('\n'.join(lines) + '\n')
tmp.chmod(0o600)
os.replace(tmp, path)
PY
if [[ -L "$base/current" ]]; then
  readlink "$base/current" > "$base/previous-release"
fi
ln -sfn "$base/releases/$release_sha" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"

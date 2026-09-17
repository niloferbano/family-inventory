# Automatic production deployment

The deployment workflow is triggered when either `tests` or `Code Quality` completes
for `main`. It verifies that both push workflows passed for the same commit in this
repository before building or deploying. Missing, running, failed, or cancelled
checks skip deployment. The latest successful completion event initiates deployment,
so either completion order works without deploying twice. A successful rerun can
trigger deployment once both checks pass.
Protect `main` with PR reviews and required `pytest`, `ruff`, and `mypy` checks.
Both images use the tested commit SHA. Deployment files come from the same commit.
The workflow serializes deployments through its production concurrency group.

Configure the GitHub `production` environment with these secrets:

- `CONTABO_HOST`: server DNS name or IPv4 address.
- `CONTABO_USER`: deployment SSH user.
- `CONTABO_SSH_KEY`: its private SSH key.
- `CONTABO_KNOWN_HOSTS`: verified OpenSSH known_hosts entry for the server. Verify
  the fingerprint through the server console before storing it; do not blindly
  trust a key collected during the deployment connection.

The deployment user needs Docker access and write access to
`/home/nilofer/family-inventory`. The server needs Bash, Docker Compose v2 supporting
`--wait` and `--wait-timeout`, Python 3, curl, tar, gzip, and GNU core utilities.
Keep `.env` and `.env.docker` in that directory, with restrictive permissions.
Configure SITE_ADDRESS and PUBLIC_BASE_URL for `https://inventory.nilofer.com`.
The public checks currently use that domain explicitly in `deploy/release.sh`.

For private GHCR packages, log in on the server as the deployment user using a
credential with read:packages access to both packages. Do not add the registry
credential to application environment files. The runner's registry login is separate.

Each release is extracted under `releases/<sha>` and links to the server environment
files. Before migrations, the script creates a custom-format PostgreSQL backup under
`backups/` and verifies the archive listing. Configure off-server backup retention
separately. Backups are not automatically deleted.

After migrations, Compose waits for service readiness. The script checks API JSON
through Caddy with bounded retries and checks frontend HTTP availability. Services
without health checks are checked for running state only. Inspect worker logs for
functional delivery verification.

On success, `.env` receives IMAGE_TAG and `current` points to the release directory.
Use the current configuration for manual operations:

```bash
cd /home/nilofer/family-inventory/current
docker compose --env-file .env -p family-inventory -f deploy/docker-compose.prod.yml ps -a
```

On failure, the workflow fails and prints container status. Inspect logs on the
server; they may contain sensitive data. No automatic schema rollback occurs.
The previous pointer is preserved, but containers or the database may already have
changed. For rollback, review migration compatibility, select the prior release
recorded in `previous-release`, and explicitly set its IMAGE_TAG when running its
Compose configuration. Restore a database backup only through a planned recovery
procedure with writers stopped. Images and volumes are not pruned by this workflow.

#!/usr/bin/env bash
# Deploy an update on the server, without needing sudo.
#   git push prod main
#   ssh 23.94.179.21 'bash ~/jbw-portfolio/deploy/update.sh'
set -o errexit
cd "$(dirname "$0")/.."

set -a; . ./.env; set +a
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
chmod -R u=rwX,go=rX staticfiles          # nginx runs as another user and must be able to read these

# A full restart, not SIGHUP. Gunicorn reloads code on SIGHUP but keeps the environment it
# started with, so changes to .env (API keys, addresses) would be silently ignored - systemd
# only reads EnvironmentFile when the service starts. Restart=always brings it straight back,
# which avoids needing sudo for systemctl.
old=$(systemctl show jbw -p MainPID --value)
kill -TERM "$old"
for _ in $(seq 1 20); do
  sleep 1
  new=$(systemctl show jbw -p MainPID --value)
  [ -n "$new" ] && [ "$new" != "0" ] && [ "$new" != "$old" ] && break
done
if [ "$new" = "$old" ] || [ -z "$new" ] || [ "$new" = "0" ]; then
  echo "jbw did not come back up - check: systemctl status jbw" >&2
  exit 1
fi
echo "restarted jbw ($old -> $new)"

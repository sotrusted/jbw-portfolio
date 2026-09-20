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

# Gunicorn reloads its workers on SIGHUP, so the new code is picked up without a sudo restart.
# (Never pkill -f on the module name here: the pattern would also match this script's own shell.)
kill -HUP "$(systemctl show jbw -p MainPID --value)"
echo "reloaded jbw"

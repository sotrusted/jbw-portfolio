#!/usr/bin/env bash
# Build step for Render (and any host with a throwaway filesystem): the database is rebuilt
# from the content fixture on every deploy, so edits made in a preview's admin don't persist.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py loaddata content

if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py createsuperuser --noinput --email "${DJANGO_SUPERUSER_EMAIL:-admin@example.com}" || true
fi

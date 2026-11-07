#!/usr/bin/env bash
# Render build step: install, collect static files, migrate, create admin, seed demo data.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py ensure_superuser
if [ "${SEED_DEMO:-false}" = "true" ]; then
  python manage.py seed_demo
fi

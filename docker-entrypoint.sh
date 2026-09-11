#!/bin/sh
# docker-entrypoint.sh
# Runs on every container start (schema.sql and seed_users.py are idempotent,
# so re-running them on restart is safe).

set -e

echo "==> Waiting for MySQL to be ready..."
until mysqladmin ping -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASSWORD" --skip-ssl --silent 2>/dev/null; do
    echo "    MySQL not yet ready — retrying in 2s"
    sleep 2
done
echo "==> MySQL is up."

echo "==> Applying schema.sql..."
mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASSWORD" --skip-ssl < /app/schema.sql
echo "==> schema.sql applied."

echo "==> Seeding users..."
python /app/seed_users.py
echo "==> Users seeded."

echo "==> Starting gunicorn..."
exec gunicorn --bind 0.0.0.0:5000 app:app

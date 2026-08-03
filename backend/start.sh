#!/bin/sh
set -e

if [ -n "$APP_DATABASE_URL" ]; then
  export DATABASE_URL="$APP_DATABASE_URL"
fi

if [ -z "$DATABASE_URL" ]; then
  if [ -n "$PGHOST" ]; then
    export DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"
  else
    echo "ERROR: No database URL found"; exit 1
  fi
else
  if echo "$DATABASE_URL" | grep -q "^postgres://"; then
    export DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|^postgres://|postgresql+asyncpg://|')
  elif echo "$DATABASE_URL" | grep -q "^postgresql://" && ! echo "$DATABASE_URL" | grep -q "+asyncpg"; then
    export DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|^postgresql://|postgresql+asyncpg://|')
  fi
fi

echo "DB: $(echo $DATABASE_URL | sed 's|:.*@|:***@|')"
echo "Running migrations..."
alembic upgrade head
echo "Starting on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
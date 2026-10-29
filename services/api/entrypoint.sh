#!/bin/sh
set -e

echo "Applying database migrations..."
alembic upgrade head

echo "Starting API application..."
exec "$@"

#!/bin/bash
set -euo pipefail

# One-time recovery for an existing MariaDB volume whose users were created
# with credentials that no longer match the deployment environment.
umask 077
cat > /tmp/reset-mariadb-credentials.sql <<SQL
ALTER USER IF EXISTS '${MARIADB_USER}'@'%' IDENTIFIED BY '${MARIADB_PASSWORD}';
ALTER USER IF EXISTS 'root'@'localhost' IDENTIFIED BY '${MARIADB_ROOT_PASSWORD}';
FLUSH PRIVILEGES;
SQL
chown mysql:mysql /tmp/reset-mariadb-credentials.sql

exec /usr/local/bin/docker-entrypoint.sh mariadbd \
  --init-file=/tmp/reset-mariadb-credentials.sql

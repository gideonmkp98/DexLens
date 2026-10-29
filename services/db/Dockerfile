ARG MARIADB_IMAGE=mariadb:11.4
FROM ${MARIADB_IMAGE}

COPY ops/reset-mariadb-credentials.sh /usr/local/bin/reset-mariadb-credentials.sh
RUN chmod 0755 /usr/local/bin/reset-mariadb-credentials.sh

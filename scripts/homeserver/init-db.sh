#!/bin/sh
set -eu
# Only executed by the official PostgreSQL entrypoint on an EMPTY volume.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_password="$SMARTSPEND_DB_PASSWORD" <<'SQL'
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE smartspend_ledger NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE smartspend LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
SELECT format('ALTER ROLE smartspend PASSWORD %L', :'app_password') \gexec
GRANT smartspend_ledger TO smartspend WITH ADMIN OPTION;
ALTER DATABASE smartspend OWNER TO smartspend;
ALTER SCHEMA public OWNER TO smartspend;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL

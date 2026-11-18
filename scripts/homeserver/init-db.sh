#!/bin/sh
set -eu
# Executed by official PostgreSQL entrypoint on an EMPTY volume; idempotent role guards included.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_password="$SMARTSPEND_DB_PASSWORD" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'smartspend_ledger') THEN
    CREATE ROLE smartspend_ledger NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'smartspend') THEN
    CREATE ROLE smartspend LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END
$$;
SELECT format('ALTER ROLE smartspend PASSWORD %L', :'app_password') \gexec
GRANT smartspend_ledger TO smartspend WITH ADMIN OPTION;
ALTER DATABASE smartspend OWNER TO smartspend;
ALTER SCHEMA public OWNER TO smartspend;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL

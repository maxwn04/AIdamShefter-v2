-- Run once as the Supabase administrative database role through verified TLS.
-- This owns cluster/database roles only. Alembic remains the sole application
-- schema/table/function/trigger migration authority.
\set ON_ERROR_STOP on

SELECT 'CREATE ROLE aidam_owner NOLOGIN NOINHERIT'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'aidam_owner'
) \gexec

SELECT 'CREATE ROLE aidam_runtime NOLOGIN NOINHERIT'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'aidam_runtime'
) \gexec

SELECT 'CREATE ROLE aidam_migrator NOLOGIN NOINHERIT'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'aidam_migrator'
) \gexec

SELECT 'CREATE ROLE aidam_api NOLOGIN INHERIT'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'aidam_api'
) \gexec

SELECT 'CREATE ROLE aidam_worker NOLOGIN INHERIT'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'aidam_worker'
) \gexec

GRANT aidam_owner TO aidam_migrator;
GRANT aidam_runtime TO aidam_api, aidam_worker;

SELECT format(
    'GRANT CONNECT, CREATE ON DATABASE %I TO aidam_owner',
    pg_catalog.current_database()
) \gexec
SELECT format(
    'GRANT CONNECT ON DATABASE %I TO aidam_migrator, aidam_api, aidam_worker',
    pg_catalog.current_database()
) \gexec

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO aidam_owner;

ALTER ROLE aidam_owner SET search_path = pg_catalog;
ALTER ROLE aidam_migrator SET search_path = pg_catalog;
ALTER ROLE aidam_runtime SET search_path = pg_catalog;
ALTER ROLE aidam_api SET search_path = pg_catalog;
ALTER ROLE aidam_worker SET search_path = pg_catalog;

ALTER ROLE aidam_api SET statement_timeout = '30s';
ALTER ROLE aidam_api SET lock_timeout = '5s';
ALTER ROLE aidam_api SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE aidam_worker SET statement_timeout = '30s';
ALTER ROLE aidam_worker SET lock_timeout = '5s';
ALTER ROLE aidam_worker SET idle_in_transaction_session_timeout = '30s';

-- Login passwords are intentionally not accepted by this file. Set them with
-- psql's interactive \password command, then enable each login explicitly.

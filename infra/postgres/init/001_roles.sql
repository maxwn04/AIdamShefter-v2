-- Local/CI-only role bootstrap. Hosted passwords come from deployment secrets.
CREATE ROLE aidam_owner NOLOGIN;
CREATE ROLE aidam_migrator LOGIN PASSWORD 'aidam_local_migrator' NOINHERIT;
CREATE ROLE aidam_runtime NOLOGIN;
CREATE ROLE aidam_api LOGIN PASSWORD 'aidam_local_api';
CREATE ROLE aidam_worker LOGIN PASSWORD 'aidam_local_worker';

GRANT aidam_owner TO aidam_migrator;
GRANT aidam_runtime TO aidam_api, aidam_worker;
GRANT CONNECT, CREATE ON DATABASE aidam TO aidam_owner;
GRANT CONNECT ON DATABASE aidam TO aidam_migrator, aidam_api, aidam_worker;
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

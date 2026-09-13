-- Run as the administrative database role before Alembic migration 0014.
-- The server must have pgvector installed. This does not grant administrative
-- privileges to application roles or relocate an existing shared extension.
\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
DO $aida$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_extension AS extension
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = extension.extnamespace
        WHERE extension.extname = 'vector' AND namespace.nspname = 'public'
    ) THEN
        RAISE EXCEPTION 'pgvector must be provisioned in public; review an existing installation before moving it';
    END IF;
    IF pg_catalog.to_regprocedure('public.vector_norm(public.vector)') IS NULL
       OR pg_catalog.to_regprocedure('public.cosine_distance(public.vector,public.vector)') IS NULL THEN
        RAISE EXCEPTION 'An administrator must upgrade pgvector to provide vector_norm and cosine_distance before migration 0014';
    END IF;
END
$aida$;
GRANT USAGE ON SCHEMA public TO aidam_owner, aidam_runtime;

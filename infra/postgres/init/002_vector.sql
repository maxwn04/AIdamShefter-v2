-- Docker entrypoint executes this as the privileged provisioning role.
-- Application migrations only consume the extension; they do not install it.
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
GRANT USAGE ON SCHEMA public TO aidam_owner, aidam_runtime;

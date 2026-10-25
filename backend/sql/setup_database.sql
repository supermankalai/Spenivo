-- Daily Spend: create the application role, databases and schema on a local PostgreSQL.
-- Run as a superuser. Safe to re-run (existing objects are kept; the password is reset).
--
--   psql -h localhost -U postgres -v app_password='<strong password>' -f backend/sql/setup_database.sql
--
-- Afterwards set DATABASE_URL in backend/.env and run `alembic upgrade head` to create the tables.

\set ON_ERROR_STOP on

-- 1. Login role used by the API (not a superuser, cannot create databases or roles).
SELECT format('CREATE ROLE daily_spend_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'daily_spend_app') \gexec
ALTER ROLE daily_spend_app WITH LOGIN PASSWORD :'app_password';

-- 2. Databases: one for the app, one for automated tests (tests migrate it up and down).
SELECT 'CREATE DATABASE daily_spend OWNER daily_spend_app ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'daily_spend') \gexec
SELECT 'CREATE DATABASE daily_spend_test OWNER daily_spend_app ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'daily_spend_test') \gexec

REVOKE ALL ON DATABASE daily_spend FROM PUBLIC;
REVOKE ALL ON DATABASE daily_spend_test FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE daily_spend TO daily_spend_app;
GRANT CONNECT, TEMPORARY ON DATABASE daily_spend_test TO daily_spend_app;

-- 3. Dedicated schema in each database; the app role's search_path points at it,
--    so Alembic creates all tables (and alembic_version) inside it.
\connect daily_spend
CREATE SCHEMA IF NOT EXISTS daily_spend AUTHORIZATION daily_spend_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER ROLE daily_spend_app IN DATABASE daily_spend SET search_path = daily_spend;

\connect daily_spend_test
CREATE SCHEMA IF NOT EXISTS daily_spend AUTHORIZATION daily_spend_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER ROLE daily_spend_app IN DATABASE daily_spend_test SET search_path = daily_spend;

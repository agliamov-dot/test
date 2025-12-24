-- Add an enum for tracking feed item ingestion status.
-- This migration is written for PostgreSQL and will safely
-- create the type only if it does not already exist.
-- It also ensures a placeholder table exists so the enum
-- is referenced somewhere concrete.

BEGIN;

DO $$
BEGIN
    CREATE TYPE feed_item_status AS ENUM ('pending', 'ingested', 'failed');
EXCEPTION
    WHEN duplicate_object THEN
        NULL;
END
$$;

CREATE TABLE IF NOT EXISTS feed_items (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    published TEXT,
    status feed_item_status NOT NULL DEFAULT 'pending'
);

COMMIT;

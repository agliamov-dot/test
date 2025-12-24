# Migrations

This repository stores database migrations as simple SQL files that can be
executed against a PostgreSQL database.

## Applying migrations

1. Connect to your PostgreSQL instance with sufficient privileges to create
   enums and tables.
2. Run each migration file in order:

   ```bash
   psql "$DATABASE_URL" -f migrations/0001_feed_item_status_enum.sql
   ```

The first migration introduces the `feed_item_status` enum with values
`pending`, `ingested`, and `failed`, and ensures a `feed_items` table exists
that uses the enum. The migration is idempotent: rerunning it will not fail if
the enum or table already exists.

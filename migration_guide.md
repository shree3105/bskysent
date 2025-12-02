# Database Migration Guide: Neon -> VPS

This guide explains how to migrate your existing data from Neon DB to your new VPS Postgres instance.

## Prerequisites

1.  **Neon Connection String**: Get this from your Neon dashboard (e.g., `postgres://user:pass@ep-xyz.aws.neon.tech/dbname`).
2.  **VPS Access**: You need SSH access to your VPS.
3.  **Docker Running**: The `db` container on your VPS must be running.

## Step 1: Direct Migration (Run on VPS)

Since you have Docker on the VPS, you can pull data directly from Neon without downloading it to your local computer first.

SSH into your VPS and run this **single command**:

```bash
# Stream data from Neon directly into your local Global DB
docker exec global-db pg_dump "your_neon_connection_string" -Fc | docker exec -i global-db pg_restore -U postgres -d bsky_sentiment --clean --if-exists --no-owner --no-privileges
```

*   Replace `"your_neon_connection_string"` with your actual Neon URL.
*   This command runs `pg_dump` inside the container (connecting to Neon) and pipes the output directly to `pg_restore` (writing to your local DB).

## Verification

Check if data exists:

```bash
docker exec global-db psql -U postgres -d bsky_sentiment -c "SELECT COUNT(*) FROM raw_posts;"
```

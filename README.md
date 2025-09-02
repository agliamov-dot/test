# RSS Aggregator MVP

This repository contains a minimal RSS aggregator service written in Python.
It stores feeds and items in PostgreSQL and provides a small CLI for managing
feeds and polling them.

## Setup

```bash
docker compose up -d db
alembic upgrade head
```

## CLI usage

```bash
python -m ingestor add-feed https://example.com/rss.xml
python -m ingestor list-feeds
python -m ingestor poll --feed-id 1
```

Configuration is read from environment variables, see `.env.example`.

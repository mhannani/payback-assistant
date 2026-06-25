# PAYBACK Assistant

A lightweight multilingual assistant that understands a shopper's intent and routes it to
products across multiple partner catalogs (dm, EDEKA, Amazon) in real time.

Given a natural-language query — in German or English — the service returns a structured
response containing either a ranked list of recommended products or a clarifying question.

> Status: early work in progress.

## Repository layout

```
apps/
  backend/    FastAPI service, catalog data pipeline, database layer, tests
  frontend/   web UI (additional, developed on a separate branch)
docker-compose.dev.yml   dev stack (API + Postgres/pgvector)
Makefile                 developer workflow (everything runs through Docker)
```

## Quick start

Requires Docker. From the repository root:

```bash
make up      # build and start the API + database
make seed    # load the partner catalogs into the database
make test    # run the test suite
```

`make help` lists all targets.

## License

MIT — see [LICENSE](LICENSE).

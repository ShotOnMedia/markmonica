# MarkMonica

MarkMonica is a mobile-first event photo and video sharing platform. Hosts create an event and share a QR code; guests scan it and upload their memories without installing an app.

## v0.1.0 Foundation

The foundation is Docker-first and contains:

- FastAPI web application
- PostgreSQL 17 + SQLAlchemy
- Alembic database migrations
- Redis queue/cache
- background worker container
- S3-compatible object storage (MinIO locally; Cloudflare R2 in production)
- automatic local bucket bootstrap
- Docker health check and dependency readiness endpoint
- GitHub Actions tests and Docker image build/publish pipeline

The initial schema already reserves the core `users`, `events`, and `media` entities so the next milestones can build on migrations rather than recreating the persistence layer.

## Local / server build

```bash
git clone https://github.com/ShotOnMedia/markmonica.git
cd markmonica
git checkout feature/v0.1.0-foundation
cp .env.example .env
# Change passwords/secrets in .env before exposing the services.
docker compose up -d --build
```

Application: `http://localhost:8000`

Liveness:

```bash
curl http://localhost:8000/health
```

Dependency readiness:

```bash
curl http://localhost:8000/health/ready
```

A healthy full stack reports database, Redis and storage as `true`.

MinIO's local administration console is exposed on port `9001`.

## Updating an existing v0.1.0 checkout

```bash
git pull
docker compose up -d --build
docker compose ps
curl http://localhost:8000/health/ready
```

Alembic migrations run automatically when the application container starts. The worker uses the same image but does not run migrations.

## Production Docker image

GitHub Actions validates feature branches. After changes land on `main`, the workflow publishes the application image to GitHub Container Registry as:

```text
ghcr.io/shotonmedia/markmonica:latest
```

Version tags such as `v0.1.0` publish corresponding semantic-version image tags. Production deployment can use the supplied override:

```bash
export MARKMONICA_VERSION=0.1.0
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

For Cloudflare R2, replace the S3 values in `.env`, normally disable `S3_AUTO_CREATE_BUCKET`, and provide an existing bucket with credentials limited to the required object operations.

## Architecture direction

Guest media will upload directly from the browser to S3-compatible object storage using short-lived presigned URLs. This keeps large photo/video transfers away from the FastAPI container. The worker will handle asynchronous jobs such as thumbnails, metadata extraction, archive generation and later video processing.

## Planned milestones

- **v0.1.0** Foundation and Docker deployment
- **v0.1.1** Host accounts and event management
- **v0.1.2** Public guest experience and QR codes
- **v0.1.3** Reliable direct photo/video uploads
- **v0.1.4** Event galleries
- **v0.1.5** Host moderation and downloads

## License

GPL-3.0

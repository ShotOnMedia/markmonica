# MarkMonica

MarkMonica is a mobile-first event photo and video sharing platform. Hosts create an event and share a QR code; guests scan it and upload their memories without installing an app.

## v0.1.0 Foundation

The first milestone establishes a deployable Docker-based application foundation:

- FastAPI application
- PostgreSQL database
- Redis for queues/cache
- S3-compatible object storage (MinIO locally; Cloudflare R2 in production)
- Docker image and Docker Compose development/deployment stack
- Health endpoint

## Quick start

```bash
git clone https://github.com/ShotOnMedia/markmonica.git
cd markmonica
git checkout feature/v0.1.0-foundation
cp .env.example .env
docker compose up -d --build
```

Open `http://localhost:8000`.

Health check:

```bash
curl http://localhost:8000/health
```

MinIO console is available locally on port `9001`.

## Architecture direction

The browser will ultimately upload media directly to S3-compatible object storage using short-lived presigned URLs. This keeps large photo/video transfers away from the application server and makes deployment and scaling considerably simpler.

Production object storage is intended to use Cloudflare R2, while local development can run entirely inside Docker with MinIO.

## Planned milestones

- **v0.1.0** Foundation and Docker deployment
- **v0.1.1** Host accounts and event management
- **v0.1.2** Public guest experience and QR codes
- **v0.1.3** Reliable photo/video uploads
- **v0.1.4** Event galleries
- **v0.1.5** Host moderation and downloads

## License

GPL-3.0

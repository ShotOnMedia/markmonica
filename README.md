# MarkMonica

MarkMonica is a mobile-first event photo and video sharing platform. Hosts create an event and share a QR code; guests scan it and upload their memories without installing an app or creating an account.

## v0.2.0

The current stack includes:

- FastAPI host and guest web application
- PostgreSQL 17 + SQLAlchemy + Alembic
- Redis-backed worker and guest upload rate limiting
- Host registration/login with DB-backed sessions
- Event creation, Draft/Live state and immutable guest slugs
- QR-code guest access
- Browser-direct photo/video uploads using short-lived S3 presigned URLs
- Upload confirmation using object HEAD verification
- Private host gallery with image previews and inline video playback
- stale upload recovery/cleanup in the worker
- security headers, same-origin protection for host mutations and hardened cookies
- dependency readiness that returns HTTP 503 when degraded

## Object storage

MarkMonica expects an external S3-compatible object store. Media bytes do not pass through FastAPI: the browser uploads directly to the object-storage endpoint using a short-lived presigned PUT URL.

The object store must:

- be reachable over HTTPS from guest browsers;
- allow CORS from `APP_URL` for `PUT`, `GET` and `HEAD` as required by the provider;
- use credentials scoped to the configured bucket and required object operations;
- keep the bucket private.

For MinIO deployments that do not implement bucket-level `PutBucketCors`, configure CORS at the MinIO server level. Cloudflare R2 can be used by replacing the S3 endpoint/credential values in `.env`.

## Deployment

```bash
git clone https://github.com/ShotOnMedia/markmonica.git
cd markmonica
cp .env.example .env
# Replace all placeholder passwords, URLs and object-storage credentials.
docker compose up -d --build
```

The application container is intended to sit behind a reverse proxy on the external Docker `proxy` network. PostgreSQL and Redis remain internal to the Compose stack.

Liveness:

```bash
curl https://events.example.com/health
```

Dependency readiness:

```bash
curl https://events.example.com/health/ready
```

A ready stack returns HTTP 200. If PostgreSQL, Redis or object storage is unavailable, readiness returns HTTP 503 with per-dependency checks.

Alembic migrations run automatically when the application container starts. The worker uses the same image with migrations disabled.

## Guest uploads

Default limits are:

- images: 50 MB;
- videos: 500 MB;
- upload session URL: 15 minutes;
- upload-init rate limit: 30 attempts per IP/event/minute;
- stale `uploading` recovery/cleanup: after 2 hours, checked every 15 minutes.

Supported image MIME types are JPEG, PNG, WebP, GIF, HEIC and HEIF. Supported video MIME types are MP4, QuickTime/MOV, M4V and WebM.

If an interrupted upload has actually reached object storage, stale cleanup validates its object size/type and promotes it to `uploaded`. If no object exists, the abandoned database row is removed.

## Production image

GitHub Actions validates changes and builds the application image. Production can use the supplied image override:

```bash
export MARKMONICA_VERSION=0.2.0
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

## Security notes

- host media URLs require an authenticated event owner and redirect to short-lived signed object URLs;
- host state-changing forms enforce same-origin requests;
- session cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` when `APP_URL` is HTTPS;
- response security headers include CSP, `nosniff`, clickjacking protection and a restrictive permissions policy;
- guest upload initiation is rate-limited with Redis;
- object-storage credentials should never be exposed to browsers or committed to the repository.

Rotate any credentials that have been exposed during development or troubleshooting before production use.

## Roadmap

- **v0.1.0** Docker/application foundation
- **v0.2.0** Host accounts, events, QR guest access, direct uploads and private host gallery
- **v0.3.0** Moderation, richer gallery workflows, bulk download and product-level polish

## License

GPL-3.0

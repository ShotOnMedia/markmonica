import logging
from pathlib import Path
import subprocess
import tempfile
import uuid

from PIL import Image, ImageOps
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Media
from app.services.storage import download_object, upload_object

logger = logging.getLogger(__name__)


def _derivative_key(media: Media, filename: str) -> str:
    parent = media.object_key.rsplit("/", 1)[0]
    return f"{parent}/derivatives/{filename}"


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=1800)


def _process_image(media: Media, workdir: Path) -> None:
    original = workdir / "original"
    preview = workdir / "preview.webp"
    download_object(media.object_key, original)

    with Image.open(original) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        image.save(preview, "WEBP", quality=82, method=6)

    preview_key = _derivative_key(media, "preview.webp")
    upload_object(preview, preview_key, "image/webp")
    media.preview_object_key = preview_key
    media.processed_content_type = "image/webp"


def _process_video(media: Media, workdir: Path) -> None:
    original = workdir / "original"
    processed = workdir / "processed.mp4"
    poster = workdir / "poster.jpg"
    download_object(media.object_key, original)

    _run([
        "ffmpeg", "-y", "-i", str(original),
        "-map", "0:v:0", "-map", "0:a?",
        "-vf", "scale='min(1280,iw)':-2",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(processed),
    ])
    _run([
        "ffmpeg", "-y", "-ss", "1", "-i", str(original),
        "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2",
        str(poster),
    ])

    processed_key = _derivative_key(media, "processed.mp4")
    poster_key = _derivative_key(media, "poster.jpg")
    upload_object(processed, processed_key, "video/mp4")
    upload_object(poster, poster_key, "image/jpeg")
    media.processed_object_key = processed_key
    media.processed_content_type = "video/mp4"
    media.poster_object_key = poster_key


def process_media(media_id: uuid.UUID | str) -> bool:
    """Create browser-friendly derivatives while always preserving the original."""
    media_uuid = uuid.UUID(str(media_id))
    with SessionLocal() as db:
        media = db.scalar(select(Media).where(Media.id == media_uuid))
        if media is None or media.status != "uploaded":
            return False
        if media.processing_status == "ready":
            return True

        media.processing_status = "processing"
        media.processing_error = None
        db.commit()

        try:
            with tempfile.TemporaryDirectory(prefix="markmonica-media-") as tmp:
                workdir = Path(tmp)
                if media.content_type.startswith("image/"):
                    _process_image(media, workdir)
                elif media.content_type.startswith("video/"):
                    _process_video(media, workdir)
                else:
                    raise ValueError(f"Unsupported media type: {media.content_type}")
            media.processing_status = "ready"
            media.processing_error = None
            db.commit()
            logger.info("Processed media %s (%s)", media.id, media.content_type)
            return True
        except Exception as exc:
            db.rollback()
            media = db.scalar(select(Media).where(Media.id == media_uuid))
            if media is not None:
                media.processing_status = "failed"
                media.processing_error = str(exc)[:2000]
                db.commit()
            logger.exception("Media processing failed for %s", media_id)
            return False


def process_next_pending() -> bool:
    """Process one uploaded item waiting for derivatives.

    Polling makes processing resilient to Redis/job-delivery failures and also
    automatically backfills existing v0.2.0 uploads after migration.
    """
    with SessionLocal() as db:
        media_id = db.scalar(
            select(Media.id)
            .where(Media.status == "uploaded", Media.processing_status == "pending")
            .order_by(Media.created_at.asc())
            .limit(1)
        )
    if media_id is None:
        return False
    process_media(media_id)
    return True

import json
import logging
import signal
import time

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services.archive import build_archive, cleanup_expired_archives, process_next_archive
from app.services.media_processing import process_media, process_next_pending
from app.services.upload_cleanup import cleanup_stale_uploads
from app.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("markmonica.worker")
running = True

def stop_worker(signum, _frame):
    global running
    logger.info("Received signal %s; stopping worker", signum)
    running = False

def handle_job(payload: str) -> None:
    job = json.loads(payload)
    job_type = job.get("type")
    if job_type == "ping":
        logger.info("Worker ping received")
        return
    if job_type == "cleanup_stale_uploads":
        cleanup_stale_uploads()
        return
    if job_type == "process_media":
        if job.get("media_id"):
            process_media(job["media_id"])
        return
    if job_type == "build_archive":
        # archive_job_id was used by the web app while older workers expected
        # job_id. Accept both so Redis delivery works immediately and the DB
        # polling fallback is only a recovery mechanism.
        job_id = job.get("job_id") or job.get("archive_job_id")
        if job_id:
            ok = build_archive(job_id)
            logger.info("Archive job %s completed=%s", job_id, ok)
        return
    logger.warning("Unknown job type: %s", job_type)

def run_cleanup() -> None:
    try:
        cleanup_stale_uploads()
    except Exception:
        logger.exception("Stale upload cleanup failed")

def run_archive_cleanup() -> None:
    try:
        cleaned = cleanup_expired_archives()
        if cleaned:
            logger.info("Expired %s generated archive(s)", cleaned)
    except Exception:
        logger.exception("Archive lifecycle cleanup failed")

def run_pending_media() -> None:
    try:
        for _ in range(3):
            if not process_next_pending():
                break
    except Exception:
        logger.exception("Pending media processing failed")

def run_pending_archives() -> None:
    try:
        for _ in range(2):
            if not process_next_archive():
                break
    except Exception:
        logger.exception("Pending archive processing failed")

def main() -> None:
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("Memories' Events worker started; queue=%s", settings.worker_queue)
    run_cleanup()
    run_archive_cleanup()
    run_pending_media()
    run_pending_archives()
    next_cleanup = time.monotonic() + settings.stale_upload_cleanup_interval_seconds
    next_archive_cleanup = time.monotonic() + settings.archive_cleanup_interval_seconds
    next_media_poll = time.monotonic() + 10
    next_archive_poll = time.monotonic() + 10
    while running:
        try:
            item = redis.blpop(settings.worker_queue, timeout=5)
            if item:
                try:
                    handle_job(item[1])
                except Exception:
                    logger.exception("Job failed")
        except RedisConnectionError:
            logger.warning("Redis unavailable; retrying in 3 seconds")
            time.sleep(3)
        if time.monotonic() >= next_media_poll:
            run_pending_media()
            next_media_poll = time.monotonic() + 10
        if time.monotonic() >= next_archive_poll:
            run_pending_archives()
            next_archive_poll = time.monotonic() + 10
        if time.monotonic() >= next_cleanup:
            run_cleanup()
            next_cleanup = time.monotonic() + settings.stale_upload_cleanup_interval_seconds
        if time.monotonic() >= next_archive_cleanup:
            run_archive_cleanup()
            next_archive_cleanup = time.monotonic() + settings.archive_cleanup_interval_seconds
    logger.info("Memories' Events worker stopped")

if __name__ == "__main__":
    main()

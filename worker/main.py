import json
import logging
import signal
import time

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

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
        media_id = job.get("media_id")
        if media_id:
            process_media(media_id)
        return
    logger.warning("Unknown job type: %s", job_type)


def run_cleanup() -> None:
    try:
        cleanup_stale_uploads()
    except Exception:
        logger.exception("Stale upload cleanup failed")


def run_pending_media() -> None:
    try:
        # Drain a small batch between queue waits so large backfills do not
        # starve normal worker jobs.
        for _ in range(3):
            if not process_next_pending():
                break
    except Exception:
        logger.exception("Pending media processing failed")


def main() -> None:
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("MarkMonica worker started; queue=%s", settings.worker_queue)

    run_cleanup()
    run_pending_media()
    next_cleanup = time.monotonic() + settings.stale_upload_cleanup_interval_seconds
    next_media_poll = time.monotonic() + 10

    while running:
        try:
            item = redis.blpop(settings.worker_queue, timeout=5)
            if item:
                _, payload = item
                try:
                    handle_job(payload)
                except Exception:
                    logger.exception("Job failed")
        except RedisConnectionError:
            logger.warning("Redis unavailable; retrying in 3 seconds")
            time.sleep(3)

        if time.monotonic() >= next_media_poll:
            run_pending_media()
            next_media_poll = time.monotonic() + 10

        if time.monotonic() >= next_cleanup:
            run_cleanup()
            next_cleanup = time.monotonic() + settings.stale_upload_cleanup_interval_seconds

    logger.info("MarkMonica worker stopped")


if __name__ == "__main__":
    main()

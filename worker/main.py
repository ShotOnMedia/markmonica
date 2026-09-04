import json
import logging
import signal
import time

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

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
    logger.warning("Unknown job type: %s", job_type)


def run_cleanup() -> None:
    try:
        cleanup_stale_uploads()
    except Exception:
        logger.exception("Stale upload cleanup failed")


def main() -> None:
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("MarkMonica worker started; queue=%s", settings.worker_queue)

    # Run once at startup, then periodically. This also recovers objects that
    # reached storage successfully but whose browser never called /confirm.
    run_cleanup()
    next_cleanup = time.monotonic() + settings.stale_upload_cleanup_interval_seconds

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

        if time.monotonic() >= next_cleanup:
            run_cleanup()
            next_cleanup = time.monotonic() + settings.stale_upload_cleanup_interval_seconds

    logger.info("MarkMonica worker stopped")


if __name__ == "__main__":
    main()

import json
import logging
import signal
import time

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

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
    logger.warning("Unknown job type: %s", job_type)


def main() -> None:
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("MarkMonica worker started; queue=%s", settings.worker_queue)

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

    logger.info("MarkMonica worker stopped")


if __name__ == "__main__":
    main()

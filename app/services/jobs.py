import json
import logging
import uuid

from redis import Redis
from redis.exceptions import RedisError

from app.settings import settings

logger = logging.getLogger(__name__)


def enqueue_media_processing(media_id: uuid.UUID | str) -> bool:
    """Queue media processing without making upload confirmation depend on Redis."""
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
        redis.rpush(settings.worker_queue, json.dumps({"type": "process_media", "media_id": str(media_id)}))
        return True
    except RedisError:
        logger.exception("Unable to queue media processing for %s", media_id)
        return False

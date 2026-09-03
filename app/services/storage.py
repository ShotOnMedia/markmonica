import logging
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from app.settings import settings

logger = logging.getLogger(__name__)


def get_s3_client():
    kwargs = {
        "service_name": "s3",
        "aws_access_key_id": settings.s3_access_key,
        "aws_secret_access_key": settings.s3_secret_key,
        "region_name": settings.s3_region,
        "config": Config(s3={"addressing_style": "path" if settings.s3_force_path_style else "virtual"}),
    }
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    return boto3.client(**kwargs)


def bucket_is_ready() -> bool:
    try:
        get_s3_client().head_bucket(Bucket=settings.s3_bucket)
        return True
    except (ClientError, EndpointConnectionError):
        return False


def ensure_bucket(max_attempts: int = 20, delay_seconds: float = 1.5) -> None:
    client = get_s3_client()

    for attempt in range(1, max_attempts + 1):
        try:
            client.head_bucket(Bucket=settings.s3_bucket)
            logger.info("Object storage bucket '%s' is ready", settings.s3_bucket)
            return
        except EndpointConnectionError:
            if attempt == max_attempts:
                raise
            logger.info("Object storage is not ready yet (%s/%s)", attempt, max_attempts)
            time.sleep(delay_seconds)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"404", "NoSuchBucket", "NotFound"} or status == 404:
                logger.info("Creating object storage bucket '%s'", settings.s3_bucket)
                client.create_bucket(Bucket=settings.s3_bucket)
                return
            raise

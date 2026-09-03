import logging
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from app.settings import settings

logger = logging.getLogger(__name__)


def _client(endpoint_url: str | None):
    kwargs = {
        "service_name": "s3",
        "aws_access_key_id": settings.s3_access_key,
        "aws_secret_access_key": settings.s3_secret_key,
        "region_name": settings.s3_region,
        "config": Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_force_path_style else "virtual"},
        ),
    }
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client(**kwargs)


def get_s3_client():
    return _client(settings.s3_endpoint_url)


def get_public_s3_client():
    return _client(settings.s3_public_endpoint_url or settings.s3_endpoint_url)


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
            _ensure_cors(client)
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
                _ensure_cors(client)
                return
            raise


def _ensure_cors(client) -> None:
    origin = settings.app_url.rstrip("/")
    try:
        client.put_bucket_cors(
            Bucket=settings.s3_bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedHeaders": ["*"],
                        "AllowedMethods": ["GET", "HEAD", "PUT"],
                        "AllowedOrigins": [origin],
                        "ExposeHeaders": ["ETag"],
                        "MaxAgeSeconds": 3600,
                    }
                ]
            },
        )
    except ClientError:
        logger.exception("Unable to configure CORS for bucket '%s'", settings.s3_bucket)
        raise


def create_presigned_upload(object_key: str, content_type: str) -> str:
    return get_public_s3_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": object_key, "ContentType": content_type},
        ExpiresIn=settings.upload_url_expiry_seconds,
    )


def create_presigned_download(object_key: str, expires_in: int = 900) -> str:
    return get_public_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": object_key},
        ExpiresIn=expires_in,
    )


def head_object(object_key: str):
    return get_s3_client().head_object(Bucket=settings.s3_bucket, Key=object_key)

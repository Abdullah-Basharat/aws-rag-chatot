import os
import tempfile
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv


load_dotenv()


S3_BUCKET = os.getenv("S3_BUCKET_NAME")
S3_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))


def _s3_client():
    """
    Return a boto3 S3 client.

    Credentials are taken from the environment / IAM role as usual.
    """
    return boto3.client("s3", region_name=S3_REGION)


def upload_fileobj(file_obj, key: str) -> str:
    """
    Upload a file-like object to S3 under the given key.

    Returns the key used (for storage in the database).
    """
    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET_NAME is not configured in the environment.")
    client = _s3_client()
    client.upload_fileobj(file_obj, S3_BUCKET, key)
    return key


def download_to_temp(key: str) -> str:
    """
    Download an S3 object to a temporary local file and return the local path.
    Caller is responsible for removing the file when done.
    """
    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET_NAME is not configured in the environment.")
    client = _s3_client()
    fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(key)[-1] or ".pdf")
    os.close(fd)
    client.download_file(S3_BUCKET, key, tmp_path)
    return tmp_path


def delete_object(key: str) -> bool:
    """
    Delete an object from S3. Returns True if delete succeeds or object is missing.
    """
    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET_NAME is not configured in the environment.")
    client = _s3_client()
    try:
        client.delete_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError:
        # Treat missing or other errors as a logical failure, but don't crash callers.
        return False


def put_text_object(key: str, content: str) -> str:
    """
    Upload a small text payload to S3 under the given key.

    This is used by the logging subsystem to store event logs in S3
    rather than on the local filesystem, keeping application nodes stateless.
    """
    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET_NAME is not configured in the environment.")
    client = _s3_client()
    client.put_object(Bucket=S3_BUCKET, Key=key, Body=content.encode("utf-8"))
    return key


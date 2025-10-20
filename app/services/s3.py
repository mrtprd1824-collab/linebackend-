# app/services/s3.py - ตัวช่วยอัปโหลดไฟล์ไปยัง S3 สำหรับเนื้อหาในระบบ
from __future__ import annotations

import mimetypes
import os
import uuid
from dataclasses import dataclass
from typing import BinaryIO, Optional

import boto3
import requests
from botocore.client import Config
from werkzeug.datastructures import FileStorage

DEFAULT_ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
DEFAULT_ALLOWED_ATTACHMENT_MIME = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


@dataclass
class S3Config:
    access_key: str
    secret_key: str
    region: str
    bucket: str
    base_url_override: Optional[str] = None
    object_acl: Optional[str] = None


def _get_env(*names: str, required: bool = True) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    if required:
        joined = " / ".join(names)
        raise RuntimeError(f"Missing AWS configuration environment variable: {joined}")
    return None


def _load_config() -> S3Config:
    access_key = _get_env("AWS_ACCESS_KEY_ID")
    secret_key = _get_env("AWS_SECRET_ACCESS_KEY")
    region = _get_env("AWS_DEFAULT_REGION", "S3_BUCKET_REGION")
    bucket = _get_env("AWS_S3_BUCKET", "S3_BUCKET_NAME")
    base_url = _get_env("AWS_S3_BASE_URL", "S3_BASE_URL", required=False)
    object_acl = _get_env("AWS_S3_OBJECT_ACL", "S3_OBJECT_ACL", required=False)

    return S3Config(
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        bucket=bucket,
        base_url_override=base_url,
        object_acl=object_acl,
    )


def _get_client(config: S3Config):
    return boto3.client(
        "s3",
        region_name=config.region,
        aws_access_key_id=config.access_key,
        aws_secret_access_key=config.secret_key,
        config=Config(signature_version="s3v4"),
    )


def _ensure_allowed(content_type: str, allowed: Optional[set[str]]) -> None:
    if allowed is None:
        return
    if content_type not in allowed:
        raise ValueError(f"Unsupported content type: {content_type}")


def _build_key(original_filename: str, key_prefix: str) -> str:
    _, ext = os.path.splitext(original_filename)
    ext = ext.lower() or ".bin"
    return f"{key_prefix.rstrip('/')}/{uuid.uuid4().hex}{ext}"


def _public_url(config: S3Config, key: str) -> str:
    if config.base_url_override:
        return f"{config.base_url_override.rstrip('/')}/{key}"
    region_part = "" if config.region == "us-east-1" else f".{config.region}"
    return f"https://{config.bucket}.s3{region_part}.amazonaws.com/{key}"


def _read_stream_with_limit(stream: BinaryIO, limit: int) -> bytes:
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("File is too large")
    return data


def upload_fileobj(
    file: FileStorage,
    key_prefix: str = "changelog/",
    allowed_mimetypes: Optional[set[str]] = None,
    max_size_bytes: int = MAX_FILE_SIZE_BYTES,
) -> str:
    """อัปโหลดไฟล์จากฟอร์มไปยัง S3 แล้วคืน URL แบบสาธารณะ"""
    if file.filename is None or file.filename == "":
        raise ValueError("Missing filename")

    if not file.mimetype:
        guessed, _ = mimetypes.guess_type(file.filename)
        mimetype = guessed or "application/octet-stream"
    else:
        mimetype = file.mimetype

    _ensure_allowed(mimetype, allowed_mimetypes or DEFAULT_ALLOWED_IMAGE_MIME)

    file.stream.seek(0)
    payload = _read_stream_with_limit(file.stream, max_size_bytes)

    config = _load_config()
    client = _get_client(config)
    key = _build_key(file.filename, key_prefix)

    extra_args = {"ContentType": mimetype}
    if config.object_acl:
        extra_args["ACL"] = config.object_acl

    client.put_object(
        Bucket=config.bucket,
        Key=key,
        Body=payload,
        **extra_args,
    )

    return _public_url(config, key)


def mirror_from_url(
    source_url: str,
    key_prefix: str = "changelog/",
    allowed_mimetypes: Optional[set[str]] = None,
    max_size_bytes: int = MAX_FILE_SIZE_BYTES,
) -> str:
    """ดาวน์โหลดภาพจาก URL แล้ว mirror ขึ้น S3"""
    response = requests.get(source_url, timeout=10)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
    if not content_type:
        guessed = mimetypes.guess_type(source_url)[0]
        content_type = guessed or "application/octet-stream"

    _ensure_allowed(content_type, allowed_mimetypes or DEFAULT_ALLOWED_IMAGE_MIME)
    if len(response.content) > max_size_bytes:
        raise ValueError("Remote file is too large")

    filename = os.path.basename(source_url.split("?")[0]) or f"image.{mimetypes.guess_extension(content_type) or 'jpg'}"

    config = _load_config()
    client = _get_client(config)
    key = _build_key(filename, key_prefix)

    extra_args = {"ContentType": content_type}
    if config.object_acl:
        extra_args["ACL"] = config.object_acl

    client.put_object(
        Bucket=config.bucket,
        Key=key,
        Body=response.content,
        **extra_args,
    )

    return _public_url(config, key)

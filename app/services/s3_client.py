import os
import mimetypes
from datetime import datetime
from uuid import uuid4

import boto3
from botocore.config import Config as BotoConfig
from flask import current_app
from werkzeug.utils import secure_filename

_s3 = None
def _client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            aws_access_key_id=current_app.config["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=current_app.config["AWS_SECRET_ACCESS_KEY"],
            region_name=current_app.config["AWS_DEFAULT_REGION"],
            config=BotoConfig(signature_version="s3v4"),
        )
    return _s3

def _bucket(): 
    return current_app.config["S3_BUCKET_NAME"]
def _prefix():
    p = current_app.config.get("S3_PREFIX", "uploads/") # กำหนด default เป็น uploads/
    return p if not p or p.endswith("/") else p + "/"

def _ctype(filename, default="application/octet-stream"):
    c, _ = mimetypes.guess_type(filename)
    return c or default

def _build_key(filename: str) -> str:
    today = datetime.utcnow().strftime("%Y/%m/%d")
    base = secure_filename(filename) or "file"
    ext = os.path.splitext(base)[1].lower()
    return f"{_prefix()}{today}/{uuid4().hex}{ext}"

def upload_fileobj(file_storage) -> str:
    key = _build_key(file_storage.filename)
    content_type = _ctype(file_storage.filename)
    _client().upload_fileobj(
        Fileobj=file_storage.stream,
        Bucket=_bucket(),
        Key=key,
        ExtraArgs={
            'ACL': 'public-read', # <-- [เพิ่ม] ทำให้ไฟล์เป็นสาธารณะ
            'ContentType': content_type
        }
    )

    region = current_app.config["AWS_DEFAULT_REGION"]
    return f"https://{_bucket()}.s3.{region}.amazonaws.com/{key}"


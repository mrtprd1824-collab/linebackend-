# app/services/__init__.py - รวม service modules ที่ใช้ข้าม blueprint
from . import s3_client  # รักษา import เดิมที่ blueprint ใช้

__all__ = ["s3_client"]

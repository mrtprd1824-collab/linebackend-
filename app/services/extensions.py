# app/services/extensions.py - รวมตัวช่วยอ้างอิง extension กลางให้ service ใช้
from app.extensions import db

# ใช้ตัวแปร Session ให้บริการดึง session ปัจจุบันจาก SQLAlchemy
Session = db.session

__all__ = ("db", "Session")

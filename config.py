import os

# สร้างตัวแปรเก็บที่อยู่หลักไว้ก่อน (ตัวพิมพ์เล็กเพราะเป็นตัวแปรช่วย ไม่ใช่ Config หลัก)
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """
    Set Flask configuration variables from .env file.
    """
    # General Config
    SECRET_KEY = os.environ.get("SECRET_KEY", "a_very_secret_key")
    FLASK_APP = os.environ.get('FLASK_APP')
    FLASK_ENV = os.environ.get('FLASK_ENV')

    # Database
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("SQLALCHEMY_DATABASE_URI")
        or os.environ.get("DATABASE_URL")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # --- ✅ UPLOAD_FOLDER ถูกย้ายเข้ามาอยู่ในนี้ และเป็นตัวพิมพ์ใหญ่ ---
    UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')

    # ... คุณสามารถเพิ่ม Config อื่นๆ ต่อท้ายในนี้ได้ ...

    BASE_URL = os.environ.get("BASE_URL", "https://linebackend-app.onrender.com/")

    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_DEFAULT_REGION = (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("S3_BUCKET_REGION")  # ตามที่พี่ตั้งใน Render
        or "ap-southeast-1"
    )
    S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
    S3_PREFIX = os.environ.get("S3_PREFIX", "uploads/")
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024
    

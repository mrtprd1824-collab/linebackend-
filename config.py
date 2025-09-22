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
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # --- ✅ UPLOAD_FOLDER ถูกย้ายเข้ามาอยู่ในนี้ และเป็นตัวพิมพ์ใหญ่ ---
    UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')

    # ... คุณสามารถเพิ่ม Config อื่นๆ ต่อท้ายในนี้ได้ ...

    BASE_URL = os.environ.get("BASE_URL", "https://442a4372ca7e.ngrok-free.app/")
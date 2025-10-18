# config.py

import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "a-default-secret-key-for-local-dev"
    FLASK_APP = os.environ.get('FLASK_APP')
    FLASK_ENV = os.environ.get('FLASK_ENV')
    BASE_URL = os.environ.get("BASE_URL", "https://linebackend-app.onrender.com/")

    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL") or
        os.environ.get("SQLALCHEMY_DATABASE_URI") or
        "sqlite:///" + os.path.abspath(os.path.join(basedir, "instance", "app.db"))
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_DEFAULT_REGION = (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("S3_BUCKET_REGION")
        or "ap-southeast-1"
    )
    S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME") or os.environ.get("AWS_S3_BUCKET")
    S3_PREFIX = os.environ.get("S3_PREFIX", "uploads/")
    
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')

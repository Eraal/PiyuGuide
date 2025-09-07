import os

class Config:
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:admin@localhost/piyuTesting'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'geraldpogi'
    # Default timezone for server-side datetime display/conversion
    # You can override via environment variable APP_TIMEZONE
    TIMEZONE = os.getenv('APP_TIMEZONE', 'Asia/Manila')
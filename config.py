import os

class Config:
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:admin@localhost/kapiyu'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'geraldpogi'
"""
Django settings for Base_Datos project.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-7x^af^92w2d9)*#1wv_nkd63u!4&uh+qgu=q$ic%4ua^d4!!yl'
DEBUG = True

# FIX: ALLOWED_HOSTS para EC2 y Docker
ALLOWED_HOSTS = os.environ.get(
    'ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0'
).split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'BD_ManejoCostos',  # FIX CRÍTICO: era 'DB_ManejoCostos' (typo), debe ser 'BD_ManejoCostos'
]

# FIX: Middleware con ControlAccesoConcurrenteMiddleware AL INICIO
MIDDLEWARE = [
    'Base_Datos.control_acceso.ControlAccesoConcurrenteMiddleware',  # ASR escalabilidad
    'Base_Datos.middleware_jwt.ValidarJWTMiddleware',              # Validación JWT (Kong)
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'Base_Datos.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'Base_Datos.wsgi.application'

# Base_Datos usa PostgreSQL (a diferencia de AWS que usa SQLite)
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     os.environ.get('DATABASE_NAME',     'bitecodb'),
        'USER':     os.environ.get('DATABASE_USER',     'postgres'),
        'PASSWORD': os.environ.get('DATABASE_PASSWORD', 'postgres'),
        'HOST':     os.environ.get('DATABASE_HOST',     'db'),
        'PORT':     os.environ.get('DATABASE_PORT',     '5432'),
        'CONN_MAX_AGE': 60,
    }
}

# FIX: Redis como backend de caché
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/3')
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        'KEY_PREFIX': 'biteco_bd',
        'TIMEOUT': 3600,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

import os
JWT_SECRET = os.environ.get('JWT_SECRET', 'biteco-jwt-secret-sprint2-2025')

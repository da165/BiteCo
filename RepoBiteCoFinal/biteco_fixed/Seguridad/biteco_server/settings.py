"""
Django settings for biteco_server project.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-+c6u+s9ztz)6!45mb7chdgz*m2^mf++r7bbm*x^4bqdq^8-7co'

DEBUG = True

# FIX: ALLOWED_HOSTS con soporte para EC2 y Docker
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
    'rest_framework',
    'seguridad',
]

# FIX: Middleware con ControlAccesoConcurrenteMiddleware AL INICIO
MIDDLEWARE = [
    'seguridad.control_acceso.ControlAccesoConcurrenteMiddleware',  # ASR escalabilidad
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'biteco_server.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'biteco_server.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME':     os.environ.get('DATABASE_NAME',     'usuariosbitecodb'),
        'USER':     os.environ.get('DATABASE_USER',     'postgres'),
        'PASSWORD': os.environ.get('DATABASE_PASSWORD', 'usuarios'),
        'HOST':     os.environ.get('DATABASE_HOST',     'db'),
        'PORT':     os.environ.get('DATABASE_PORT',     '5432'),
        'CONN_MAX_AGE': 60,
    }
}

# FIX: Redis como backend de caché (requerido para el middleware de escalabilidad)
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/1')
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        'KEY_PREFIX': 'biteco_seg',
        'TIMEOUT': 600,
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
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '[{asctime}] [{levelname}] {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
    },
    'loggers': {
        'control_acceso': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}

# JWT — Usado por views.py para firmar tokens que Kong valida
JWT_SECRET = os.environ.get("JWT_SECRET", "biteco-jwt-secret-sprint2-2025")

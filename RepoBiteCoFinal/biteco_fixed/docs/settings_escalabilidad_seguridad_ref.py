"""
settings_escalabilidad.py
=========================
Añadir estas secciones al settings.py de CADA microservicio
para soportar el ASR de escalabilidad.

En settings.py, añadir al final:
  from .settings_escalabilidad import *

O copiar y pegar las secciones relevantes directamente.
"""

import os

# =============================================================================
# 1. MIDDLEWARE — Registrar el control de acceso concurrente
# =============================================================================
# Añadir AL INICIO del MIDDLEWARE list (debe ser el primero para que
# el circuit breaker y el semáforo actúen antes de cualquier procesamiento):
#
# MIDDLEWARE = [
#     'middleware.control_acceso.ControlAccesoConcurrenteMiddleware',  # <-- PRIMERO
#     'django.middleware.security.SecurityMiddleware',
#     ...
# ]
#
# O usando la variable de entorno para activar/desactivar:

MIDDLEWARE_ESCALABILIDAD = [
    'middleware.control_acceso.ControlAccesoConcurrenteMiddleware',
]

# =============================================================================
# 2. CACHÉ — Redis para compartir el contador entre workers de Gunicorn
# =============================================================================
# CRÍTICO: Con django.core.cache.backends.locmem.LocMemCache cada worker
# tiene su propio contador → el semáforo no funciona correctamente.
# Usar Redis para estado compartido entre todos los workers.

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/1')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'biteco',
        'TIMEOUT': 600,  # 10 minutos — coincide con la ventana del ASR
    }
}

# =============================================================================
# 3. ALLOWED_HOSTS — Necesario para Gunicorn en producción
# =============================================================================
ALLOWED_HOSTS = os.environ.get(
    'ALLOWED_HOSTS',
    'localhost,127.0.0.1,0.0.0.0'
).split(',')

# =============================================================================
# 4. DATABASE — Connection pooling para aguantar 5000 usuarios
# =============================================================================
# Con 5000 usuarios y 9 workers × 4 threads = 36 conexiones concurrentes
# PostgreSQL por defecto aguanta 100 conexiones. Para 5000+ usuarios
# necesitamos pgBouncer o aumentar max_connections en PostgreSQL.
#
# Configuración recomendada para la EC2 de BD:
#   max_connections = 200  (en postgresql.conf)
#   shared_buffers  = 256MB

DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     os.environ.get('DATABASE_NAME',     'usuariosbitecodb'),
        'USER':     os.environ.get('DATABASE_USER',     'postgres'),
        'PASSWORD': os.environ.get('DATABASE_PASSWORD', 'usuarios'),
        'HOST':     os.environ.get('DATABASE_HOST',     'db'),
        'PORT':     os.environ.get('DATABASE_PORT',     '5432'),
        'CONN_MAX_AGE': 60,   # Reutilizar conexiones (reduce overhead)
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# =============================================================================
# 5. URLS — Registrar el endpoint de health check
# =============================================================================
# Añadir en urls.py:
#
# from middleware.control_acceso import health_check
# urlpatterns = [
#     ...
#     path('health/', health_check, name='health_check'),
# ]

# =============================================================================
# 6. LOGGING — Para monitorear el middleware durante las pruebas
# =============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] [{levelname}] {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class':     'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'control_acceso': {
            'handlers':  ['console'],
            'level':     'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers':  ['console'],
            'level':     'WARNING',
            'propagate': False,
        },
    },
}

# =============================================================================
# 7. SECURITY — Deshabilitar CSRF para APIs (ya manejado por Kong/API Gateway)
# =============================================================================
# El middleware csrf puede añadir latencia innecesaria en APIs puras.
# Solo deshabilitar si el acceso pasa siempre por Kong con autenticación.
#
# MIDDLEWARE = [m for m in MIDDLEWARE if 'CsrfViewMiddleware' not in m]

# =============================================================================
# INSTRUCCIONES DE INSTALACIÓN RÁPIDA
# =============================================================================
"""
PARA SEGURIDAD (biteco_server/settings.py):
-------------------------------------------
1. Copiar middleware/control_acceso.py → Seguridad/middleware/control_acceso.py
2. Crear Seguridad/middleware/__init__.py (vacío)
3. Añadir al settings.py:

   MIDDLEWARE = [
       'middleware.control_acceso.ControlAccesoConcurrenteMiddleware',
       ...  # resto del middleware existente
   ]

   CACHES = {
       'default': {
           'BACKEND': 'django.core.cache.backends.redis.RedisCache',
           'LOCATION': 'redis://redis:6379/1',
       }
   }

4. Añadir al urls.py:
   from middleware.control_acceso import health_check
   path('health/', health_check),

5. Añadir al requirements.txt:
   gunicorn
   django-redis
   redis

6. Levantar con docker-compose.escalabilidad.yml

PARA BASE_DATOS y AWS: mismo procedimiento.
"""

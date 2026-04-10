"""
Kong/middleware_jwt.py — Middleware de validación JWT para Base_Datos y AWS
============================================================================
Cuando Kong está activo, él mismo valida el JWT antes de reenviar la petición
al microservicio destino. Sin embargo, para pruebas locales o acceso directo,
este middleware valida el token en cada microservicio.

Instalación en Base_Datos/Base_Datos/settings.py y AWS/AWS/settings.py:
    MIDDLEWARE = [
        'Base_Datos.middleware_jwt.ValidarJWTMiddleware',  # o AWS.middleware_jwt
        ...
    ]
    JWT_SECRET = os.environ.get("JWT_SECRET", "biteco-jwt-secret-sprint2-2025")

Rutas excluidas (no requieren JWT):
    /health/  /admin/  /metrics/
"""

import jwt
import os
import logging
from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger("middleware_jwt")

RUTAS_PUBLICAS = ("/health/", "/admin/", "/metrics/", "/favicon.ico")


class ValidarJWTMiddleware:
    """
    Valida el token JWT en el header Authorization: Bearer <token>
    antes de pasar la petición a la view.

    Kong ya hace esta validación antes de llegar aquí en producción.
    Este middleware es la segunda línea de defensa (defense in depth).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.secret = getattr(settings, "JWT_SECRET",
                              os.environ.get("JWT_SECRET", "biteco-jwt-secret-sprint2-2025"))

    def __call__(self, request):
        # Rutas que no requieren autenticación
        if any(request.path.startswith(r) for r in RUTAS_PUBLICAS):
            return self.get_response(request)

        # Extraer y validar el token
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        # Si viene de Kong, el header X-Kong-Consumer-Username indica
        # que Kong ya validó el token — no validamos de nuevo
        if request.META.get("HTTP_X_KONG_CONSUMER_USERNAME"):
            return self.get_response(request)

        if not auth_header.startswith("Bearer "):
            return JsonResponse(
                {
                    "error": "Autenticación requerida. Incluye el header: Authorization: Bearer <token>",
                    "hint":  "Obtén el token en POST /auth/login/ a través de Kong",
                },
                status=401,
            )

        token = auth_header[7:]
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
            # Inyectar el payload en el request para que las views lo usen si lo necesitan
            request.jwt_payload = payload
            return self.get_response(request)

        except jwt.ExpiredSignatureError:
            return JsonResponse({"error": "Token expirado. Vuelve a hacer login."}, status=401)
        except jwt.InvalidTokenError as e:
            logger.warning(f"[JWT] Token inválido: {e}")
            return JsonResponse({"error": "Token inválido."}, status=401)

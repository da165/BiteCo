"""
middleware/control_acceso.py
============================
Táctica de Escalabilidad: Control de Acceso Concurrente
ASR: Gestionar 5000 usuarios concurrentes, picos de hasta 12000,
     en ventana de 10 minutos, con tasa de error <= 10%.

Implementa tres mecanismos combinados:

1. SEMÁFORO DE CONCURRENCIA (Throttle activo)
   - Contador atómico de requests en vuelo usando Redis (o cache Django).
   - Si usuarios_activos >= UMBRAL_NORMAL (5000): modo degradado (solo caché).
   - Si usuarios_activos >= UMBRAL_PICO   (12000): responde 503 inmediatamente.

2. RATE LIMITER POR VENTANA DESLIZANTE (10 minutos)
   - Cuenta requests por IP en ventana de 600 segundos.
   - Limita abuso de un solo cliente.

3. CIRCUIT BREAKER (protección de backend)
   - Si la tasa de error supera 10% en los últimos 60s: abre el circuito
     y devuelve 503 sin tocar el backend hasta que se enfríe.

Instalación en cada microservicio:
   MIDDLEWARE = [
       ...
       'ruta.al.middleware.control_acceso.ControlAccesoConcurrenteMiddleware',
   ]

Headers de respuesta expuestos:
   X-Concurrent-Users: número actual de usuarios activos
   X-Circuit-State: CLOSED | OPEN | HALF_OPEN
   X-RateLimit-Remaining: requests restantes en la ventana actual
"""

import time
import threading
import logging
from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger("control_acceso")

# ---------------------------------------------------------------------------
# Constantes del ASR
# ---------------------------------------------------------------------------
UMBRAL_NORMAL      = 5_000    # A partir de aquí: modo degradado
UMBRAL_PICO        = 12_000   # A partir de aquí: rechazo inmediato (503)
VENTANA_SEGUNDOS   = 600      # 10 minutos (ventana del ASR)
MAX_ERROR_RATE     = 0.10     # 10% tasa de error máxima permitida
CIRCUIT_VENTANA    = 60       # segundos para medir tasa de error del circuit breaker
CIRCUIT_MIN_REQS   = 100      # mínimo de requests para activar el circuit breaker
RATE_LIMIT_IP      = 3_000    # max requests por IP en la ventana de 10 min

# Claves Redis/cache
KEY_ACTIVOS        = "cc:usuarios_activos"
KEY_CIRCUIT_STATE  = "cc:circuit_state"
KEY_CIRCUIT_ERRORS = "cc:circuit_errors"
KEY_CIRCUIT_TOTAL  = "cc:circuit_total"
KEY_CIRCUIT_OPEN_AT= "cc:circuit_open_at"

# ---------------------------------------------------------------------------
# Helpers thread-safe para el contador de concurrencia
# ---------------------------------------------------------------------------
_local_lock = threading.Lock()


def _incrementar_activos() -> int:
    """Incrementa el contador de usuarios activos y retorna el nuevo valor."""
    with _local_lock:
        actual = cache.get(KEY_ACTIVOS, 0)
        nuevo = actual + 1
        cache.set(KEY_ACTIVOS, nuevo, timeout=VENTANA_SEGUNDOS * 2)
        return nuevo


def _decrementar_activos():
    """Decrementa el contador de usuarios activos (llamado en finally)."""
    with _local_lock:
        actual = cache.get(KEY_ACTIVOS, 0)
        nuevo = max(0, actual - 1)
        cache.set(KEY_ACTIVOS, nuevo, timeout=VENTANA_SEGUNDOS * 2)


def get_usuarios_activos() -> int:
    """Retorna el número actual de usuarios activos (para tests y monitoreo)."""
    return cache.get(KEY_ACTIVOS, 0)


def reset_contadores():
    """Reinicia todos los contadores. Útil para setUp/tearDown en tests."""
    cache.delete(KEY_ACTIVOS)
    cache.delete(KEY_CIRCUIT_STATE)
    cache.delete(KEY_CIRCUIT_ERRORS)
    cache.delete(KEY_CIRCUIT_TOTAL)
    cache.delete(KEY_CIRCUIT_OPEN_AT)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------
class CircuitBreaker:
    CLOSED    = "CLOSED"
    OPEN      = "OPEN"
    HALF_OPEN = "HALF_OPEN"
    COOLDOWN  = 30  # segundos antes de pasar a HALF_OPEN

    @classmethod
    def estado(cls) -> str:
        estado = cache.get(KEY_CIRCUIT_STATE, cls.CLOSED)
        if estado == cls.OPEN:
            # Verificar si ya expiró el cooldown
            open_at = cache.get(KEY_CIRCUIT_OPEN_AT, 0)
            if time.time() - open_at >= cls.COOLDOWN:
                cache.set(KEY_CIRCUIT_STATE, cls.HALF_OPEN, timeout=VENTANA_SEGUNDOS)
                return cls.HALF_OPEN
        return estado

    @classmethod
    def registrar_resultado(cls, es_error: bool):
        """Registra el resultado de un request y actualiza el estado."""
        total  = cache.get(KEY_CIRCUIT_TOTAL, 0) + 1
        errors = cache.get(KEY_CIRCUIT_ERRORS, 0) + (1 if es_error else 0)

        cache.set(KEY_CIRCUIT_TOTAL,  total,  timeout=CIRCUIT_VENTANA)
        cache.set(KEY_CIRCUIT_ERRORS, errors, timeout=CIRCUIT_VENTANA)

        if total >= CIRCUIT_MIN_REQS:
            tasa = errors / total
            estado_actual = cache.get(KEY_CIRCUIT_STATE, cls.CLOSED)

            if tasa > MAX_ERROR_RATE and estado_actual == cls.CLOSED:
                logger.warning(
                    f"[CircuitBreaker] ABRIENDO circuito. "
                    f"Tasa de error: {tasa:.1%} ({errors}/{total})"
                )
                cache.set(KEY_CIRCUIT_STATE,  cls.OPEN, timeout=VENTANA_SEGUNDOS)
                cache.set(KEY_CIRCUIT_OPEN_AT, time.time(), timeout=VENTANA_SEGUNDOS)

            elif tasa <= MAX_ERROR_RATE and estado_actual in (cls.OPEN, cls.HALF_OPEN):
                logger.info(
                    f"[CircuitBreaker] CERRANDO circuito. "
                    f"Tasa de error recuperada: {tasa:.1%}"
                )
                cache.set(KEY_CIRCUIT_STATE, cls.CLOSED, timeout=VENTANA_SEGUNDOS)
                # Reset contadores para nueva ventana
                cache.set(KEY_CIRCUIT_TOTAL,  0, timeout=CIRCUIT_VENTANA)
                cache.set(KEY_CIRCUIT_ERRORS, 0, timeout=CIRCUIT_VENTANA)

    @classmethod
    def tasa_error_actual(cls) -> float:
        total  = cache.get(KEY_CIRCUIT_TOTAL, 0)
        errors = cache.get(KEY_CIRCUIT_ERRORS, 0)
        return errors / total if total > 0 else 0.0


# ---------------------------------------------------------------------------
# Rate Limiter por IP (ventana fija de 10 min)
# ---------------------------------------------------------------------------
def _verificar_rate_limit(ip: str) -> tuple[bool, int]:
    """
    Retorna (permitido, requests_restantes).
    """
    key = f"cc:rl:{ip}"
    count = cache.get(key, 0) + 1
    cache.set(key, count, timeout=VENTANA_SEGUNDOS)
    restantes = max(0, RATE_LIMIT_IP - count)
    return count <= RATE_LIMIT_IP, restantes


# ---------------------------------------------------------------------------
# Middleware principal
# ---------------------------------------------------------------------------
class ControlAccesoConcurrenteMiddleware:
    """
    Middleware de control de acceso concurrente para el ASR de escalabilidad.

    Orden de verificación:
    1. Rutas excluidas (health check, admin) → pasan siempre.
    2. Circuit Breaker OPEN → 503 inmediato.
    3. Umbral de pico (>= 12000) → 503.
    4. Rate limit por IP superado → 429.
    5. Umbral normal (>= 5000) → modo degradado (solo caché).
    6. Request normal → procesar con contador activo.
    """

    RUTAS_EXCLUIDAS = ("/health/", "/admin/", "/metrics/", "/favicon.ico")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 0. Excluir rutas de monitoreo
        if any(request.path.startswith(r) for r in self.RUTAS_EXCLUIDAS):
            return self.get_response(request)

        # 1. Circuit Breaker
        estado_cb = CircuitBreaker.estado()
        if estado_cb == CircuitBreaker.OPEN:
            logger.warning(f"[Middleware] Circuito ABIERTO — rechazando {request.path}")
            return JsonResponse(
                {
                    "error": "Servicio temporalmente no disponible (circuit breaker activo)",
                    "estado_circuito": estado_cb,
                    "retry_after": CircuitBreaker.COOLDOWN,
                },
                status=503,
                headers={"Retry-After": str(CircuitBreaker.COOLDOWN)},
            )

        # 2. Rate limit por IP
        ip = self._obtener_ip(request)
        permitido, restantes = _verificar_rate_limit(ip)
        if not permitido:
            return JsonResponse(
                {
                    "error": "Rate limit excedido. Intenta en la próxima ventana de 10 minutos.",
                    "retry_after": VENTANA_SEGUNDOS,
                },
                status=429,
                headers={
                    "Retry-After": str(VENTANA_SEGUNDOS),
                    "X-RateLimit-Remaining": "0",
                },
            )

        # 3. Verificar umbral de pico (12000)
        activos = get_usuarios_activos()
        if activos >= UMBRAL_PICO:
            logger.error(
                f"[Middleware] PICO SUPERADO: {activos} usuarios activos. "
                f"Rechazando request de {ip}"
            )
            CircuitBreaker.registrar_resultado(es_error=True)
            return JsonResponse(
                {
                    "error": "Sistema en sobrecarga. Capacidad máxima alcanzada.",
                    "usuarios_activos": activos,
                    "umbral_pico": UMBRAL_PICO,
                    "retry_after": 60,
                },
                status=503,
                headers={
                    "Retry-After": "60",
                    "X-Concurrent-Users": str(activos),
                },
            )

        # 4. Modo degradado (5000 <= activos < 12000)
        modo_degradado = activos >= UMBRAL_NORMAL
        if modo_degradado:
            logger.warning(
                f"[Middleware] MODO DEGRADADO: {activos} usuarios activos."
            )
            request.META["X_MODO_DEGRADADO"] = True

        # 5. Procesar request normal con contador activo
        activos_con_este = _incrementar_activos()
        response = None
        try:
            response = self.get_response(request)
            es_error = response.status_code >= 500
            CircuitBreaker.registrar_resultado(es_error=es_error)
            return response
        except Exception as exc:
            CircuitBreaker.registrar_resultado(es_error=True)
            logger.error(f"[Middleware] Excepción en request: {exc}")
            raise
        finally:
            _decrementar_activos()
            if response is not None:
                response["X-Concurrent-Users"]  = str(activos_con_este)
                response["X-Circuit-State"]      = CircuitBreaker.estado()
                response["X-RateLimit-Remaining"] = str(restantes)

    @staticmethod
    def _obtener_ip(request) -> str:
        """Extrae la IP real considerando proxies (X-Forwarded-For de Kong/ALB)."""
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")


# ---------------------------------------------------------------------------
# Endpoint de health check y métricas (agregar a urls.py)
# ---------------------------------------------------------------------------
def health_check(request):
    """GET /health/ — Retorna estado del sistema para monitoreo."""
    activos = get_usuarios_activos()
    estado_cb = CircuitBreaker.estado()
    tasa_error = CircuitBreaker.tasa_error_actual()

    estado_sistema = "ok"
    if activos >= UMBRAL_PICO:
        estado_sistema = "sobrecarga"
    elif activos >= UMBRAL_NORMAL:
        estado_sistema = "degradado"
    elif estado_cb != CircuitBreaker.CLOSED:
        estado_sistema = "degradado"

    return JsonResponse(
        {
            "estado": estado_sistema,
            "usuarios_activos": activos,
            "umbral_normal": UMBRAL_NORMAL,
            "umbral_pico": UMBRAL_PICO,
            "circuit_breaker": estado_cb,
            "tasa_error_actual": round(tasa_error, 4),
            "tasa_error_maxima": MAX_ERROR_RATE,
        },
        status=200 if estado_sistema == "ok" else 206,
    )

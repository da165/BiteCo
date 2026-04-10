"""
tests/test_control_acceso.py
============================
Tests del middleware ControlAccesoConcurrenteMiddleware
ASR: 5000 usuarios nominales, 12000 pico, ventana 10 min, error <= 10%

Cómo ejecutar:
  # Copiar middleware/control_acceso.py al proyecto Django objetivo, luego:
  python manage.py test tests.test_control_acceso -v 2

Requiere en settings.py (para tests):
  CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
  MIDDLEWARE incluye 'ruta.control_acceso.ControlAccesoConcurrenteMiddleware'
"""

import json
import threading
import time
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory, override_settings
from django.http import HttpResponse
from django.core.cache import cache

from middleware.control_acceso import (
    ControlAccesoConcurrenteMiddleware,
    CircuitBreaker,
    get_usuarios_activos,
    reset_contadores,
    _incrementar_activos,
    _decrementar_activos,
    UMBRAL_NORMAL,
    UMBRAL_PICO,
    MAX_ERROR_RATE,
    VENTANA_SEGUNDOS,
    KEY_ACTIVOS,
    health_check,
)


# ---------------------------------------------------------------------------
# Helpers de test
# ---------------------------------------------------------------------------
def _respuesta_ok(_request):
    return HttpResponse("OK", status=200)


def _respuesta_error(_request):
    return HttpResponse("Error", status=500)


def _make_middleware(get_response=None):
    return ControlAccesoConcurrenteMiddleware(get_response or _respuesta_ok)


# ===========================================================================
# 1. TESTS DEL CONTADOR DE CONCURRENCIA
# ===========================================================================
class TestContadorConcurrencia(TestCase):

    def setUp(self):
        reset_contadores()

    def tearDown(self):
        reset_contadores()

    def test_inicia_en_cero(self):
        """El contador de usuarios activos comienza en 0."""
        self.assertEqual(get_usuarios_activos(), 0)

    def test_incremento_y_decremento(self):
        """Incrementar y decrementar es simétrico."""
        _incrementar_activos()
        _incrementar_activos()
        self.assertEqual(get_usuarios_activos(), 2)
        _decrementar_activos()
        self.assertEqual(get_usuarios_activos(), 1)
        _decrementar_activos()
        self.assertEqual(get_usuarios_activos(), 0)

    def test_decremento_no_baja_de_cero(self):
        """El contador nunca se vuelve negativo."""
        _decrementar_activos()
        _decrementar_activos()
        self.assertEqual(get_usuarios_activos(), 0)

    def test_incremento_thread_safe(self):
        """
        100 threads incrementando simultáneamente → contador = 100.
        Verifica que no hay race conditions.
        """
        reset_contadores()
        resultados = []

        def incrementar():
            val = _incrementar_activos()
            resultados.append(val)

        threads = [threading.Thread(target=incrementar) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(get_usuarios_activos(), 100)
        # Todos los valores deben ser únicos (no hay dos threads con el mismo valor)
        # En la práctica puede haber colisiones por el lock, pero el final debe ser 100
        self.assertEqual(len(resultados), 100)

    def test_reset_limpia_todo(self):
        """reset_contadores() pone todo a cero."""
        _incrementar_activos()
        _incrementar_activos()
        CircuitBreaker.registrar_resultado(es_error=True)
        reset_contadores()
        self.assertEqual(get_usuarios_activos(), 0)
        self.assertEqual(CircuitBreaker.estado(), CircuitBreaker.CLOSED)


# ===========================================================================
# 2. TESTS DEL CIRCUIT BREAKER
# ===========================================================================
class TestCircuitBreaker(TestCase):

    def setUp(self):
        reset_contadores()

    def tearDown(self):
        reset_contadores()

    def test_estado_inicial_cerrado(self):
        """El circuit breaker empieza en estado CLOSED."""
        self.assertEqual(CircuitBreaker.estado(), CircuitBreaker.CLOSED)

    def test_no_abre_con_pocos_requests(self):
        """
        Con menos de CIRCUIT_MIN_REQS requests, el circuito no se abre
        aunque todos sean errores. Evita falsos positivos al arrancar.
        """
        for _ in range(50):
            CircuitBreaker.registrar_resultado(es_error=True)
        self.assertEqual(CircuitBreaker.estado(), CircuitBreaker.CLOSED)

    def test_abre_cuando_tasa_error_supera_10_pct(self):
        """
        Con 100+ requests y tasa de error > 10%, el circuito se abre.
        """
        # 85 exitosos + 15 errores = 15% error → debe abrir
        for _ in range(85):
            CircuitBreaker.registrar_resultado(es_error=False)
        for _ in range(15):
            CircuitBreaker.registrar_resultado(es_error=True)

        self.assertEqual(CircuitBreaker.estado(), CircuitBreaker.OPEN)

    def test_no_abre_con_exactamente_10_pct_error(self):
        """
        Con exactamente 10% de errores, el circuito NO debe abrirse
        (el ASR dice 'no mayor a 10%', o sea > 10% lo activa).
        """
        for _ in range(90):
            CircuitBreaker.registrar_resultado(es_error=False)
        for _ in range(10):
            CircuitBreaker.registrar_resultado(es_error=True)

        # 10% exacto es el límite — no debe abrir
        self.assertNotEqual(CircuitBreaker.estado(), CircuitBreaker.OPEN)

    def test_tasa_error_calculada_correctamente(self):
        """La tasa de error se calcula como errores/total."""
        for _ in range(80):
            CircuitBreaker.registrar_resultado(es_error=False)
        for _ in range(20):
            CircuitBreaker.registrar_resultado(es_error=True)

        tasa = CircuitBreaker.tasa_error_actual()
        self.assertAlmostEqual(tasa, 0.20, places=2)

    def test_transicion_a_half_open_despues_de_cooldown(self):
        """Después del cooldown, el circuito pasa de OPEN a HALF_OPEN."""
        # Abrir el circuito
        for _ in range(100):
            CircuitBreaker.registrar_resultado(es_error=True)
        self.assertEqual(CircuitBreaker.estado(), CircuitBreaker.OPEN)

        # Simular que pasó el cooldown
        open_at_viejo = time.time() - (CircuitBreaker.COOLDOWN + 5)
        cache.set("cc:circuit_open_at", open_at_viejo, timeout=600)

        self.assertEqual(CircuitBreaker.estado(), CircuitBreaker.HALF_OPEN)

    def test_cierra_cuando_tasa_se_recupera(self):
        """
        Si la tasa de error baja del umbral (después de un pico),
        el circuito vuelve a CLOSED.
        """
        # Llevar a OPEN
        for _ in range(90):
            CircuitBreaker.registrar_resultado(es_error=True)
        for _ in range(10):
            CircuitBreaker.registrar_resultado(es_error=False)

        # Simular cooldown
        cache.set("cc:circuit_open_at", time.time() - 40, timeout=600)
        self.assertEqual(CircuitBreaker.estado(), CircuitBreaker.HALF_OPEN)

        # Ahora llega una avalancha de requests exitosos → cierra
        reset_contadores()
        for _ in range(200):
            CircuitBreaker.registrar_resultado(es_error=False)

        self.assertEqual(CircuitBreaker.estado(), CircuitBreaker.CLOSED)


# ===========================================================================
# 3. TESTS DEL MIDDLEWARE — FLUJO NORMAL
# ===========================================================================
class TestMiddlewareFlujoNormal(TestCase):

    def setUp(self):
        reset_contadores()
        self.factory = RequestFactory()

    def tearDown(self):
        reset_contadores()

    def test_request_normal_retorna_200(self):
        """Un request normal pasa el middleware y retorna 200."""
        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/reportes/proj-001/2025-01/")
        response = mw(req)
        self.assertEqual(response.status_code, 200)

    def test_headers_x_concurrent_users_presentes(self):
        """El middleware añade el header X-Concurrent-Users a la respuesta."""
        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/reportes/proj-001/2025-01/")
        response = mw(req)
        self.assertIn("X-Concurrent-Users", response)

    def test_headers_x_circuit_state_presente(self):
        """El middleware añade el header X-Circuit-State."""
        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/reportes/proj-001/2025-01/")
        response = mw(req)
        self.assertIn("X-Circuit-State", response)
        self.assertEqual(response["X-Circuit-State"], CircuitBreaker.CLOSED)

    def test_contador_vuelve_a_cero_despues_del_request(self):
        """
        El contador de activos se decrementa cuando el request termina.
        Garantiza que no hay fugas de concurrencia.
        """
        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/test/")

        self.assertEqual(get_usuarios_activos(), 0)
        mw(req)
        self.assertEqual(get_usuarios_activos(), 0)

    def test_contador_decrementa_aunque_view_lance_excepcion(self):
        """
        Si la view lanza una excepción, el finally del middleware
        garantiza que el contador se decrementa de todas formas.
        """
        def vista_explosiva(_req):
            raise ValueError("Error inesperado en la view")

        mw = _make_middleware(vista_explosiva)
        req = self.factory.get("/api/test/")

        with self.assertRaises(ValueError):
            mw(req)

        self.assertEqual(get_usuarios_activos(), 0)

    def test_rutas_excluidas_no_cuentan(self):
        """Las rutas de health check y admin no se cuentan en el semáforo."""
        mw = _make_middleware(_respuesta_ok)

        for ruta in ["/health/", "/admin/dashboard/", "/metrics/"]:
            req = self.factory.get(ruta)
            mw(req)

        self.assertEqual(get_usuarios_activos(), 0)


# ===========================================================================
# 4. TESTS DEL MIDDLEWARE — UMBRAL NORMAL (5000 usuarios)
# ===========================================================================
class TestMiddlewareUmbralNormal(TestCase):

    def setUp(self):
        reset_contadores()
        self.factory = RequestFactory()

    def tearDown(self):
        reset_contadores()

    def _simular_usuarios_activos(self, n: int):
        """Pone el contador directamente en n sin threads."""
        cache.set(KEY_ACTIVOS, n, timeout=VENTANA_SEGUNDOS * 2)

    def test_modo_degradado_activa_en_5000(self):
        """
        Con 5000 usuarios activos, el request sigue procesándose
        pero se activa el modo degradado (flag en request.META).
        """
        self._simular_usuarios_activos(UMBRAL_NORMAL)

        flag_recibido = []

        def vista_que_lee_flag(request):
            flag_recibido.append(request.META.get("X_MODO_DEGRADADO", False))
            return HttpResponse("OK degradado", status=200)

        mw = _make_middleware(vista_que_lee_flag)
        req = self.factory.get("/api/reportes/proj-001/2025-01/")
        response = mw(req)

        # Aún responde 200 (no rechaza)
        self.assertEqual(response.status_code, 200)
        # Flag de modo degradado activado
        self.assertTrue(flag_recibido[0])

    def test_modo_degradado_sigue_respondiendo(self):
        """
        Entre 5000 y 11999 usuarios, el sistema devuelve 200
        (no 503). El ASR exige gestionar esos usuarios, no rechazarlos.
        """
        self._simular_usuarios_activos(UMBRAL_NORMAL + 1000)  # 6000

        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/reportes/proj-001/2025-01/")
        response = mw(req)

        self.assertEqual(response.status_code, 200)

    def test_umbral_normal_exacto_activa_degradado(self):
        """Exactamente en 5000 usuarios se activa el modo degradado."""
        self._simular_usuarios_activos(UMBRAL_NORMAL)

        flags = []

        def vista_check(request):
            flags.append(request.META.get("X_MODO_DEGRADADO", False))
            return HttpResponse("ok", status=200)

        mw = _make_middleware(vista_check)
        req = self.factory.get("/api/test/")
        mw(req)

        self.assertTrue(flags[0])


# ===========================================================================
# 5. TESTS DEL MIDDLEWARE — UMBRAL PICO (12000 usuarios)
# ===========================================================================
class TestMiddlewareUmbralPico(TestCase):

    def setUp(self):
        reset_contadores()
        self.factory = RequestFactory()

    def tearDown(self):
        reset_contadores()

    def _simular_usuarios_activos(self, n: int):
        cache.set(KEY_ACTIVOS, n, timeout=VENTANA_SEGUNDOS * 2)

    def test_rechazo_503_en_umbral_pico(self):
        """
        Con 12000 usuarios activos, el middleware rechaza con 503
        sin llegar a la view.
        """
        self._simular_usuarios_activos(UMBRAL_PICO)

        vista_llamada = []

        def vista_que_no_debe_llamarse(_req):
            vista_llamada.append(True)
            return HttpResponse("nunca", status=200)

        mw = _make_middleware(vista_que_no_debe_llamarse)
        req = self.factory.get("/api/reportes/proj-001/2025-01/")
        response = mw(req)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(vista_llamada), 0)

    def test_respuesta_503_tiene_mensaje_claro(self):
        """La respuesta 503 incluye información útil para el cliente."""
        self._simular_usuarios_activos(UMBRAL_PICO)

        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/test/")
        response = mw(req)

        data = json.loads(response.content)
        self.assertIn("error", data)
        self.assertIn("usuarios_activos", data)
        self.assertIn("retry_after", data)

    def test_header_retry_after_presente_en_503(self):
        """La respuesta 503 incluye el header Retry-After."""
        self._simular_usuarios_activos(UMBRAL_PICO)

        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/test/")
        response = mw(req)

        self.assertIn("Retry-After", response)

    def test_rechazo_no_decrementa_contador(self):
        """
        Cuando se rechaza por pico, el contador NO se incrementó
        (el request nunca entró al semáforo).
        """
        self._simular_usuarios_activos(UMBRAL_PICO)
        activos_antes = get_usuarios_activos()

        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/test/")
        mw(req)

        # El contador sigue igual (no subió ni bajó por este request)
        self.assertEqual(get_usuarios_activos(), activos_antes)

    def test_pico_supera_umbral_en_1(self):
        """12001 usuarios también es rechazado."""
        self._simular_usuarios_activos(UMBRAL_PICO + 1)

        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/test/")
        response = mw(req)
        self.assertEqual(response.status_code, 503)


# ===========================================================================
# 6. TESTS DEL CIRCUIT BREAKER EN EL MIDDLEWARE
# ===========================================================================
class TestMiddlewareCircuitBreaker(TestCase):

    def setUp(self):
        reset_contadores()
        self.factory = RequestFactory()

    def tearDown(self):
        reset_contadores()

    def _abrir_circuito(self):
        """Helper: abre el circuito con suficientes errores."""
        from middleware.control_acceso import CIRCUIT_MIN_REQS, KEY_CIRCUIT_STATE, KEY_CIRCUIT_OPEN_AT
        cache.set(KEY_CIRCUIT_STATE,   CircuitBreaker.OPEN,  timeout=600)
        cache.set(KEY_CIRCUIT_OPEN_AT, time.time(),          timeout=600)

    def test_circuito_abierto_retorna_503_sin_procesar(self):
        """Con circuito abierto, el middleware retorna 503 inmediatamente."""
        self._abrir_circuito()

        vista_llamada = []

        def vista(_req):
            vista_llamada.append(True)
            return HttpResponse("ok", status=200)

        mw = _make_middleware(vista)
        req = self.factory.get("/api/test/")
        response = mw(req)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(vista_llamada), 0)

    def test_respuesta_503_circuito_indica_estado(self):
        """La respuesta 503 de circuito abierto incluye el estado del circuito."""
        self._abrir_circuito()

        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/test/")
        response = mw(req)

        data = json.loads(response.content)
        self.assertIn("estado_circuito", data)
        self.assertEqual(data["estado_circuito"], CircuitBreaker.OPEN)

    def test_errors_en_view_incrementan_contador_circuit_breaker(self):
        """Los status 5xx de las views alimentan el circuit breaker."""
        mw = _make_middleware(_respuesta_error)

        for _ in range(150):
            req = self.factory.get("/api/test/")
            mw(req)

        # Con 150 errores de 150 requests (100% error), debe estar abierto
        self.assertEqual(CircuitBreaker.estado(), CircuitBreaker.OPEN)


# ===========================================================================
# 7. TESTS DEL RATE LIMITER
# ===========================================================================
class TestRateLimiter(TestCase):

    def setUp(self):
        reset_contadores()
        cache.clear()
        self.factory = RequestFactory()

    def tearDown(self):
        cache.clear()

    def test_requests_dentro_del_limite_pasan(self):
        """Un usuario dentro del rate limit recibe 200."""
        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/test/", REMOTE_ADDR="10.0.0.1")
        response = mw(req)
        self.assertEqual(response.status_code, 200)

    def test_header_ratelimit_remaining_decrece(self):
        """El header X-RateLimit-Remaining disminuye con cada request."""
        mw = _make_middleware(_respuesta_ok)

        req1 = self.factory.get("/api/test/", REMOTE_ADDR="10.0.0.2")
        r1 = mw(req1)
        rem1 = int(r1.get("X-RateLimit-Remaining", 0))

        req2 = self.factory.get("/api/test/", REMOTE_ADDR="10.0.0.2")
        r2 = mw(req2)
        rem2 = int(r2.get("X-RateLimit-Remaining", 0))

        self.assertGreater(rem1, rem2)

    def test_ips_distintas_tienen_limites_independientes(self):
        """Cada IP tiene su propio contador de rate limit."""
        from middleware.control_acceso import RATE_LIMIT_IP, KEY_ACTIVOS
        # Saturar IP A
        cache.set("cc:rl:192.168.1.1", RATE_LIMIT_IP, timeout=VENTANA_SEGUNDOS)

        mw = _make_middleware(_respuesta_ok)

        # IP A: debe dar 429
        req_a = self.factory.get("/api/test/", REMOTE_ADDR="192.168.1.1")
        resp_a = mw(req_a)
        self.assertEqual(resp_a.status_code, 429)

        # IP B: debe pasar normalmente
        req_b = self.factory.get("/api/test/", REMOTE_ADDR="192.168.1.2")
        resp_b = mw(req_b)
        self.assertEqual(resp_b.status_code, 200)

    def test_429_tiene_retry_after(self):
        """La respuesta 429 incluye Retry-After."""
        from middleware.control_acceso import RATE_LIMIT_IP
        cache.set("cc:rl:10.1.1.1", RATE_LIMIT_IP + 1, timeout=VENTANA_SEGUNDOS)

        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/test/", REMOTE_ADDR="10.1.1.1")
        response = mw(req)

        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)


# ===========================================================================
# 8. TESTS DEL HEALTH CHECK ENDPOINT
# ===========================================================================
class TestHealthCheck(TestCase):

    def setUp(self):
        reset_contadores()
        self.factory = RequestFactory()

    def tearDown(self):
        reset_contadores()

    def test_health_ok_cuando_sin_carga(self):
        """Sin carga, el health check retorna estado 'ok'."""
        req = self.factory.get("/health/")
        response = health_check(req)
        data = json.loads(response.content)
        self.assertEqual(data["estado"], "ok")

    def test_health_degradado_en_umbral_normal(self):
        """Con 5000+ usuarios, el health check indica estado 'degradado'."""
        cache.set(KEY_ACTIVOS, UMBRAL_NORMAL, timeout=600)
        req = self.factory.get("/health/")
        response = health_check(req)
        data = json.loads(response.content)
        self.assertEqual(data["estado"], "degradado")

    def test_health_sobrecarga_en_umbral_pico(self):
        """Con 12000+ usuarios, el health check indica 'sobrecarga'."""
        cache.set(KEY_ACTIVOS, UMBRAL_PICO, timeout=600)
        req = self.factory.get("/health/")
        response = health_check(req)
        data = json.loads(response.content)
        self.assertEqual(data["estado"], "sobrecarga")

    def test_health_incluye_metricas_clave(self):
        """El health check expone todas las métricas del ASR."""
        req = self.factory.get("/health/")
        response = health_check(req)
        data = json.loads(response.content)

        for campo in [
            "usuarios_activos", "umbral_normal", "umbral_pico",
            "circuit_breaker", "tasa_error_actual", "tasa_error_maxima"
        ]:
            self.assertIn(campo, data, msg=f"Falta campo '{campo}' en health check")


# ===========================================================================
# 9. TESTS DE CONCURRENCIA REAL (threading)
# ===========================================================================
class TestConcurrenciaReal(TestCase):
    """
    Simula requests concurrentes reales usando threading.
    Estos tests validan que el middleware es thread-safe bajo carga.
    """

    def setUp(self):
        reset_contadores()
        self.factory = RequestFactory()

    def tearDown(self):
        reset_contadores()

    def test_100_threads_concurrentes_no_producen_leak(self):
        """
        100 threads haciendo requests simultáneos.
        Al terminar todos, el contador debe ser 0.
        """
        mw = _make_middleware(_respuesta_ok)
        errors = []

        def hacer_request():
            try:
                req = self.factory.get("/api/test/")
                mw(req)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=hacer_request) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, msg=f"Errores inesperados: {errors}")
        self.assertEqual(
            get_usuarios_activos(), 0,
            msg="Leak de concurrencia: el contador no volvió a 0"
        )

    def test_500_threads_concurrentes_sin_crash(self):
        """
        500 threads concurrentes — todos deben terminar sin excepción.
        Valida estabilidad básica debajo del umbral normal (5000).
        """
        mw = _make_middleware(_respuesta_ok)
        completados = []
        errors = []

        def hacer_request():
            try:
                req = self.factory.get("/api/test/")
                resp = mw(req)
                completados.append(resp.status_code)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=hacer_request) for _ in range(500)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(completados), 500)
        self.assertEqual(get_usuarios_activos(), 0)

    def test_pico_rechaza_correctamente_en_concurrencia(self):
        """
        Con el contador en umbral pico, todos los threads concurrentes
        reciben 503 (ninguno pasa).
        """
        cache.set(KEY_ACTIVOS, UMBRAL_PICO, timeout=600)
        mw = _make_middleware(_respuesta_ok)
        respuestas = []

        def hacer_request():
            req = self.factory.get("/api/test/")
            resp = mw(req)
            respuestas.append(resp.status_code)

        threads = [threading.Thread(target=hacer_request) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Todos deben ser 503
        self.assertTrue(
            all(s == 503 for s in respuestas),
            msg=f"Algunos requests pasaron en pico: {set(respuestas)}"
        )


# ===========================================================================
# 10. TEST DE ACEPTACIÓN DEL ASR
# ===========================================================================
class TestAceptacionASR(TestCase):
    """
    Test de aceptación que verifica los criterios exactos del ASR:
    - 5000 usuarios nominales gestionados (sin rechazo)
    - 12000 usuarios pico con error <= 10%
    - Ventana de 10 minutos
    """

    def setUp(self):
        reset_contadores()
        self.factory = RequestFactory()

    def tearDown(self):
        reset_contadores()

    def test_asr_5000_usuarios_nominales_no_son_rechazados(self):
        """
        ASR Criterio 1: 5000 usuarios concurrentes son GESTIONADOS.
        El sistema NO rechaza requests en el nivel nominal.
        """
        # Simular 4999 usuarios ya activos (justo debajo del pico)
        cache.set(KEY_ACTIVOS, UMBRAL_NORMAL - 1, timeout=600)

        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/reportes/proj/2025-01/")
        response = mw(req)

        self.assertNotEqual(
            response.status_code, 503,
            msg="El sistema rechazó un request con menos de 5000 usuarios — FALLA ASR"
        )

    def test_asr_tasa_error_maxima_10pct(self):
        """
        ASR Criterio 2: La tasa de error no debe superar el 10%.
        Verifica que el circuit breaker se activa exactamente en > 10%.
        """
        # 89 exitosos + 11 errores = 11% → debe activar el circuit breaker
        for _ in range(89):
            CircuitBreaker.registrar_resultado(es_error=False)
        for _ in range(11):
            CircuitBreaker.registrar_resultado(es_error=True)

        tasa = CircuitBreaker.tasa_error_actual()
        estado = CircuitBreaker.estado()

        self.assertGreater(tasa, MAX_ERROR_RATE,
            msg=f"Tasa de error {tasa:.1%} debería superar {MAX_ERROR_RATE:.0%}")
        self.assertEqual(estado, CircuitBreaker.OPEN,
            msg="El circuit breaker debería haberse abierto con > 10% errores")

    def test_asr_ventana_10_minutos(self):
        """
        ASR Criterio 3: La ventana de medición es 10 minutos (600 segundos).
        Verifica que los contadores tienen el TTL correcto.
        """
        self.assertEqual(
            VENTANA_SEGUNDOS, 600,
            msg=f"La ventana debe ser 600s (10 min), es {VENTANA_SEGUNDOS}s"
        )

    def test_asr_pico_12000_retorna_503_con_mensaje(self):
        """
        ASR Criterio 4: En pico de 12000, el sistema responde 503
        con información para que el cliente pueda reintentar.
        """
        cache.set(KEY_ACTIVOS, UMBRAL_PICO, timeout=600)

        mw = _make_middleware(_respuesta_ok)
        req = self.factory.get("/api/test/")
        response = mw(req)

        data = json.loads(response.content)

        self.assertEqual(response.status_code, 503)
        self.assertIn("retry_after", data,
            msg="El 503 debe incluir 'retry_after' para que el cliente sepa cuándo reintentar")
        self.assertIn("X-Concurrent-Users", response,
            msg="El header X-Concurrent-Users debe estar presente en el 503")

    def test_asr_umbrales_configurados_correctamente(self):
        """
        Verifica que los umbrales del middleware coinciden exactamente
        con los valores del ASR.
        """
        self.assertEqual(UMBRAL_NORMAL, 5_000,
            msg=f"Umbral normal debe ser 5000, es {UMBRAL_NORMAL}")
        self.assertEqual(UMBRAL_PICO, 12_000,
            msg=f"Umbral pico debe ser 12000, es {UMBRAL_PICO}")
        self.assertEqual(MAX_ERROR_RATE, 0.10,
            msg=f"Tasa de error máxima debe ser 0.10, es {MAX_ERROR_RATE}")
        self.assertEqual(VENTANA_SEGUNDOS, 600,
            msg=f"Ventana debe ser 600s, es {VENTANA_SEGUNDOS}")

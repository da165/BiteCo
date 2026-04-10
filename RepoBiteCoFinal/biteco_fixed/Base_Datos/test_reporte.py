"""
Tests Unitarios - Microservicio Base_Datos (Orquestador)
ASR: Latencia < 100ms, Cache-hit, fallback a BD y a microservicio AWS.

El orquestador implementa 3 niveles de consulta:
  1. Cache (Redis/LocMem) → más rápido
  2. Base de Datos (PostgreSQL) → si no hay cache
  3. Microservicio AWS (requests.get) → si no hay en BD

Ejecutar con:
    python manage.py test BD_ManejoCostos
  o:
    pytest tests/base_datos/test_reporte.py -v
"""

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.core.cache import cache
from BD_ManejoCostos.models import ReporteGasto


class ConsultarReporteTests(TestCase):
    """
    Suite de pruebas para GET /api/reportes/<project_id>/<mes>/

    Usa Django TestCase para tener BD aislada por test.
    El cache se limpia en setUp() para garantizar aislamiento.
    """

    def setUp(self):
        self.client = Client()
        cache.clear()  # Limpiar cache entre tests para aislamiento
        self.project_id = "proyecto-test-001"
        self.mes = "2024-11"
        self.url = f"/api/reportes/{self.project_id}/{self.mes}/"
        self.datos_reporte = {
            "proveedor_a": 500.0,
            "proveedor_b": 300.0,
            "proveedor_c": 200.0,
            "total": 1000.0
        }

    def tearDown(self):
        cache.clear()

    # ------------------------------------------------------------------
    # ESCENARIO 1: Cache HIT → respuesta inmediata (< 100ms esperado)
    # ------------------------------------------------------------------
    def test_cache_hit_retorna_200_con_origen_cache(self):
        """
        Dado que el reporte está en caché,
        Cuando se consulta el endpoint,
        Debe retornar HTTP 200 con origen='cache' (camino más rápido).
        """
        cache_key = f"reporte_{self.project_id}_{self.mes}"
        cache.set(cache_key, self.datos_reporte, timeout=3600)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["origen"], "cache")
        self.assertEqual(data["data"], self.datos_reporte)

    def test_cache_hit_no_consulta_base_de_datos(self):
        """
        Con cache hit, NO debe acceder a la BD.
        Verificamos que ReporteGasto.objects.get NO se llama.
        """
        cache_key = f"reporte_{self.project_id}_{self.mes}"
        cache.set(cache_key, self.datos_reporte, timeout=3600)

        with patch("BD_ManejoCostos.views.ReporteGasto.objects.get") as mock_get:
            self.client.get(self.url)
            mock_get.assert_not_called()

    # ------------------------------------------------------------------
    # ESCENARIO 2: Cache MISS → buscar en Base de Datos
    # ------------------------------------------------------------------
    def test_bd_hit_retorna_200_con_origen_base_de_datos(self):
        """
        Dado que no hay cache pero sí existe el reporte en la BD,
        Debe retornar HTTP 200 con origen='base_de_datos'.
        """
        ReporteGasto.objects.create(
            project_id=self.project_id,
            mes=self.mes,
            datos_json=self.datos_reporte
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["origen"], "base_de_datos")
        self.assertEqual(data["data"], self.datos_reporte)

    def test_bd_hit_guarda_resultado_en_cache(self):
        """
        Al obtener un reporte de la BD, debe guardarlo en caché
        para que la siguiente petición sea más rápida (táctica de cache).
        """
        ReporteGasto.objects.create(
            project_id=self.project_id,
            mes=self.mes,
            datos_json=self.datos_reporte
        )

        self.client.get(self.url)

        cache_key = f"reporte_{self.project_id}_{self.mes}"
        cached = cache.get(cache_key)
        self.assertIsNotNone(cached, "El resultado debería quedar en caché")
        self.assertEqual(cached, self.datos_reporte)

    # ------------------------------------------------------------------
    # ESCENARIO 3: Cache MISS + BD MISS → llamar microservicio AWS
    # ------------------------------------------------------------------
    @patch("BD_ManejoCostos.views.requests.get")
    def test_microservicio_aws_exitoso_retorna_200(self, mock_requests_get):
        """
        Dado que no hay cache ni BD,
        Cuando el microservicio AWS responde OK,
        Debe retornar HTTP 200 con origen='microservicio_aws'.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.datos_reporte
        mock_requests_get.return_value = mock_response

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["origen"], "microservicio_aws")

    @patch("BD_ManejoCostos.views.requests.get")
    def test_microservicio_aws_guarda_en_bd(self, mock_requests_get):
        """
        Al obtener datos del microservicio AWS,
        Debe persistirlos en la BD local para futuras consultas.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.datos_reporte
        mock_requests_get.return_value = mock_response

        self.client.get(self.url)

        existe = ReporteGasto.objects.filter(
            project_id=self.project_id,
            mes=self.mes
        ).exists()
        self.assertTrue(existe, "El reporte debe persistirse en la BD")

    @patch("BD_ManejoCostos.views.requests.get")
    def test_microservicio_aws_guarda_en_cache(self, mock_requests_get):
        """Al obtener de AWS, también debe cachear para la siguiente petición."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.datos_reporte
        mock_requests_get.return_value = mock_response

        self.client.get(self.url)

        cache_key = f"reporte_{self.project_id}_{self.mes}"
        cached = cache.get(cache_key)
        self.assertIsNotNone(cached)

    # ------------------------------------------------------------------
    # ESCENARIO 4: Microservicio AWS falla → 404
    # ------------------------------------------------------------------
    @patch("BD_ManejoCostos.views.requests.get")
    def test_microservicio_aws_retorna_error_da_404(self, mock_requests_get):
        """
        Cuando el microservicio AWS retorna un código != 200,
        El orquestador debe retornar HTTP 404.
        """
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_requests_get.return_value = mock_response

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    @patch("BD_ManejoCostos.views.requests.get")
    def test_falla_de_conexion_con_aws_da_503(self, mock_requests_get):
        """
        Cuando no se puede conectar con el microservicio AWS
        (timeout, red caída, etc.),
        Debe retornar HTTP 503 Service Unavailable.
        """
        import requests as req_lib
        mock_requests_get.side_effect = req_lib.exceptions.RequestException(
            "Connection refused"
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 503)

    # ------------------------------------------------------------------
    # ESCENARIO 5: Segunda llamada usa caché (verifica cache funciona)
    # ------------------------------------------------------------------
    @patch("BD_ManejoCostos.views.requests.get")
    def test_segunda_llamada_usa_cache_no_aws(self, mock_requests_get):
        """
        Dado que la primera llamada trae datos de AWS (y cachea),
        La segunda llamada NO debe llamar a requests.get de nuevo.
        Esto valida la táctica de caché para reducir latencia.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.datos_reporte
        mock_requests_get.return_value = mock_response

        # Primera llamada: va a AWS
        self.client.get(self.url)
        self.assertEqual(mock_requests_get.call_count, 1)

        # Segunda llamada: debe usar caché
        response2 = self.client.get(self.url)
        self.assertEqual(mock_requests_get.call_count, 1)  # No se llamó de nuevo
        self.assertEqual(response2.json()["origen"], "cache")

    # ------------------------------------------------------------------
    # ESCENARIO 6: Diferentes combinaciones de project_id y mes
    # ------------------------------------------------------------------
    def test_diferentes_meses_son_independientes(self):
        """
        Reportes de diferentes meses deben almacenarse y recuperarse
        de forma independiente.
        """
        ReporteGasto.objects.create(
            project_id=self.project_id,
            mes="2024-10",
            datos_json={"total": 800.0}
        )
        ReporteGasto.objects.create(
            project_id=self.project_id,
            mes="2024-11",
            datos_json={"total": 1000.0}
        )

        resp_oct = self.client.get(f"/api/reportes/{self.project_id}/2024-10/")
        resp_nov = self.client.get(f"/api/reportes/{self.project_id}/2024-11/")

        self.assertEqual(resp_oct.json()["data"]["total"], 800.0)
        self.assertEqual(resp_nov.json()["data"]["total"], 1000.0)

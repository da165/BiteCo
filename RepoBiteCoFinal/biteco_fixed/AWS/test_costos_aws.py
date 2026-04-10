"""
Tests Unitarios - Microservicio AWS_Consulta
ASR: Consulta de costos a AWS Cost Explorer

IMPORTANTE: Este microservicio llama a boto3 (AWS real).
Los tests usan `unittest.mock` para interceptar boto3 y NO hacer
llamadas reales a AWS. Esto permite correr los tests sin credenciales.

Ejecutar con:
    python manage.py test AWS_Consulta
  o:
    pytest tests/aws/test_costos_aws.py -v
"""

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from botocore.exceptions import ClientError


class ObtenerCostosAWSTests(TestCase):
    """
    Suite de pruebas para GET /api/aws/costos/<project_id>/
    Se mockea boto3.client para evitar llamadas reales a AWS.
    """

    def setUp(self):
        self.client = Client()
        self.url = "/api/aws/costos/proyecto-001/"

        # Respuesta simulada de AWS Cost Explorer
        self.mock_aws_response = {
            "ResultsByTime": [
                {
                    "Total": {
                        "UnblendedCost": {
                            "Amount": "1234.56",
                            "Unit": "USD"
                        }
                    }
                }
            ]
        }

    # ------------------------------------------------------------------
    # ESCENARIO 1: Consulta exitosa a AWS → 200 OK
    # ------------------------------------------------------------------
    @patch("AWS_Consulta.views.boto3.client")
    def test_consulta_exitosa_retorna_200(self, mock_boto_client):
        """
        Dado que AWS Cost Explorer responde correctamente,
        Debe retornar HTTP 200 con el costo en la respuesta.
        """
        # Configurar el mock para que get_cost_and_usage retorne datos válidos
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = self.mock_aws_response
        mock_boto_client.return_value = mock_ce

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["costo_total"], "1234.56")
        self.assertEqual(data["moneda"], "USD")

    @patch("AWS_Consulta.views.boto3.client")
    def test_consulta_retorna_project_id_correcto(self, mock_boto_client):
        """La respuesta debe incluir el project_id solicitado."""
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = self.mock_aws_response
        mock_boto_client.return_value = mock_ce

        response = self.client.get("/api/aws/costos/mi-proyecto-xyz/")
        data = response.json()

        self.assertEqual(data["project_id"], "mi-proyecto-xyz")

    @patch("AWS_Consulta.views.boto3.client")
    def test_se_llama_a_aws_con_region_us_east_1(self, mock_boto_client):
        """
        El cliente boto3 debe inicializarse con region_name='us-east-1'
        según la configuración del experimento.
        """
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = self.mock_aws_response
        mock_boto_client.return_value = mock_ce

        self.client.get(self.url)

        mock_boto_client.assert_called_once_with("ce", region_name="us-east-1")

    # ------------------------------------------------------------------
    # ESCENARIO 2: AWS devuelve error (ClientError) → 500
    # ------------------------------------------------------------------
    @patch("AWS_Consulta.views.boto3.client")
    def test_error_aws_retorna_500(self, mock_boto_client):
        """
        Cuando AWS Cost Explorer lanza un ClientError,
        Debe retornar HTTP 500 con status 'error'.
        """
        mock_ce = MagicMock()
        # Simular un error de AWS (ej: credenciales inválidas, permisos)
        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "User is not authorized to perform: ce:GetCostAndUsage"
            }
        }
        mock_ce.get_cost_and_usage.side_effect = ClientError(
            error_response, "GetCostAndUsage"
        )
        mock_boto_client.return_value = mock_ce

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertIn("message", data)

    @patch("AWS_Consulta.views.boto3.client")
    def test_error_aws_incluye_mensaje_descriptivo(self, mock_boto_client):
        """El mensaje de error debe ser descriptivo (no vacío)."""
        mock_ce = MagicMock()
        error_response = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
        mock_ce.get_cost_and_usage.side_effect = ClientError(error_response, "GetCostAndUsage")
        mock_boto_client.return_value = mock_ce

        response = self.client.get(self.url)
        data = response.json()

        self.assertTrue(len(data.get("message", "")) > 0)

    # ------------------------------------------------------------------
    # ESCENARIO 3: Estructura de la respuesta JSON
    # ------------------------------------------------------------------
    @patch("AWS_Consulta.views.boto3.client")
    def test_respuesta_contiene_campos_requeridos(self, mock_boto_client):
        """
        La respuesta exitosa debe tener: status, project_id, costo_total, moneda.
        Esto garantiza compatibilidad con el Orquestador (Base_Datos).
        """
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = self.mock_aws_response
        mock_boto_client.return_value = mock_ce

        response = self.client.get(self.url)
        data = response.json()

        campos_requeridos = ["status", "project_id", "costo_total", "moneda"]
        for campo in campos_requeridos:
            with self.subTest(campo=campo):
                self.assertIn(campo, data, f"Falta campo: {campo}")

    @patch("AWS_Consulta.views.boto3.client")
    def test_costo_total_es_valor_numerico_como_string(self, mock_boto_client):
        """
        AWS devuelve el Amount como string numérico.
        Verificar que no se pierde la precisión en la respuesta.
        """
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = {
            "ResultsByTime": [{
                "Total": {"UnblendedCost": {"Amount": "999999.99", "Unit": "USD"}}
            }]
        }
        mock_boto_client.return_value = mock_ce

        response = self.client.get(self.url)
        data = response.json()

        self.assertEqual(data["costo_total"], "999999.99")

    # ------------------------------------------------------------------
    # ESCENARIO 4: Diferentes project_ids en la URL
    # ------------------------------------------------------------------
    @patch("AWS_Consulta.views.boto3.client")
    def test_project_id_con_guiones_y_numeros(self, mock_boto_client):
        """La URL debe aceptar project_ids con guiones y números."""
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = self.mock_aws_response
        mock_boto_client.return_value = mock_ce

        response = self.client.get("/api/aws/costos/proyecto-A-2024/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project_id"], "proyecto-A-2024")

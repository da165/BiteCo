"""
Tests Unitarios - Microservicio Seguridad
ASR: Autenticación de usuarios vía POST /auth/login/

Ejecutar con:
    python manage.py test seguridad
  o con pytest:
    pytest tests/seguridad/test_login.py -v
"""

import json
from django.test import TestCase, Client
from django.contrib.auth.models import User


class LoginViewTests(TestCase):
    """
    Suite de pruebas para el endpoint POST /auth/login/
    Cubre los escenarios documentados en el Diseño de Experimento.
    """

    def setUp(self):
        """Crear usuario de prueba antes de cada test."""
        self.client = Client()
        self.url = "/auth/login/"
        self.usuario = User.objects.create_user(
            username="usuario@biteco.com",
            email="usuario@biteco.com",
            password="password123"
        )

    # ------------------------------------------------------------------
    # ESCENARIO 1: Credenciales válidas → 200 OK
    # ------------------------------------------------------------------
    def test_login_exitoso_retorna_200(self):
        """
        Dado un usuario registrado,
        Cuando envía credenciales correctas,
        Debe retornar HTTP 200 y status 'success'.
        """
        payload = {
            "email": "usuario@biteco.com",
            "password": "password123"
        }
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["mensaje"], "Acceso concedido")

    def test_login_exitoso_retorna_nombre_usuario(self):
        """
        Dado un login exitoso,
        La respuesta debe incluir el campo 'usuario' con el username correcto.
        """
        payload = {"email": "usuario@biteco.com", "password": "password123"}
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json"
        )
        data = response.json()
        self.assertIn("usuario", data)
        self.assertEqual(data["usuario"], "usuario@biteco.com")

    # ------------------------------------------------------------------
    # ESCENARIO 2: Credenciales inválidas → 401 Unauthorized
    # ------------------------------------------------------------------
    def test_login_password_incorrecta_retorna_401(self):
        """
        Dado un usuario válido,
        Cuando envía una contraseña incorrecta,
        Debe retornar HTTP 401 con mensaje de error.
        """
        payload = {"email": "usuario@biteco.com", "password": "mal_password"}
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "Credenciales inválidas")

    def test_login_usuario_inexistente_retorna_401(self):
        """
        Dado un email que no existe en la BD,
        Debe retornar HTTP 401.
        """
        payload = {"email": "noexiste@biteco.com", "password": "cualquier"}
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 401)

    # ------------------------------------------------------------------
    # ESCENARIO 3: Método incorrecto → 405 Method Not Allowed
    # ------------------------------------------------------------------
    def test_login_con_GET_retorna_405(self):
        """
        Cuando se accede con método GET,
        Debe retornar HTTP 405 Method Not Allowed.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        data = response.json()
        self.assertIn("error", data)

    def test_login_con_PUT_retorna_405(self):
        """PUT tampoco debe estar permitido."""
        response = self.client.put(self.url, data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 405)

    # ------------------------------------------------------------------
    # ESCENARIO 4: Body malformado → 400 Bad Request
    # ------------------------------------------------------------------
    def test_login_body_json_invalido_retorna_400(self):
        """
        Cuando el body no es JSON válido,
        Debe retornar HTTP 400.
        """
        response = self.client.post(
            self.url,
            data="esto_no_es_json",
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_login_sin_campo_email_retorna_401(self):
        """
        Cuando falta el campo email,
        authenticate() recibe None y debe retornar 401.
        """
        payload = {"password": "password123"}
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json"
        )
        # authenticate() con username=None retorna None → 401
        self.assertEqual(response.status_code, 401)

    def test_login_sin_campo_password_retorna_401(self):
        """Cuando falta la contraseña, debe retornar 401."""
        payload = {"email": "usuario@biteco.com"}
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 401)

    # ------------------------------------------------------------------
    # ESCENARIO 5: Respuesta es siempre JSON
    # ------------------------------------------------------------------
    def test_login_response_content_type_es_json(self):
        """El Content-Type de la respuesta debe ser application/json."""
        payload = {"email": "usuario@biteco.com", "password": "password123"}
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertIn("application/json", response["Content-Type"])

"""
views.py — Microservicio de Seguridad
=======================================
Endpoints:
  POST /auth/login/     — Autenticar usuario, retorna token JWT
  POST /auth/registro/  — Registrar nuevo usuario
  GET  /auth/perfil/    — Datos del usuario autenticado (requiere token)
  POST /auth/logout/    — Invalidar sesión

El token JWT es el que Kong usa para validar peticiones
a los demás microservicios (Base_Datos, AWS).
"""

import json
import jwt
import datetime
import os

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

# Clave secreta para firmar los JWT — en producción usar variable de entorno
JWT_SECRET  = os.environ.get("JWT_SECRET", "biteco-jwt-secret-sprint2-2025")
JWT_ALGO    = "HS256"
JWT_EXPIRY_H = 8  # horas de validez del token


def _generar_token(user: User) -> str:
    """Genera un token JWT firmado para el usuario autenticado."""
    payload = {
        "sub":      user.username,          # subject (identificador)
        "user_id":  user.id,
        "email":    user.email,
        "is_staff": user.is_staff,
        "iat":      datetime.datetime.utcnow(),
        "exp":      datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRY_H),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def _verificar_token(request) -> dict | None:
    """
    Extrae y verifica el JWT del header Authorization: Bearer <token>.
    Retorna el payload decodificado o None si es inválido/ausente.
    """
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ─────────────────────────────────────────────────────────────
# POST /auth/login/
# Usado por Kong como upstream del servicio de autenticación.
# Kong valida credenciales aquí y obtiene el JWT para el cliente.
# ─────────────────────────────────────────────────────────────
@csrf_exempt
def login_usuario(request):
    if request.method != "POST":
        return JsonResponse({"error": "Metodo no permitido"}, status=405)
    try:
        data     = json.loads(request.body)
        email    = data.get("email")
        password = data.get("password")

        user = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)
            token = _generar_token(user)
            return JsonResponse({
                "mensaje":   "Acceso concedido",
                "usuario":   user.username,
                "status":    "success",
                "token":     token,           # JWT para usar en Kong
                "expira_en": f"{JWT_EXPIRY_H}h",
            }, status=200)
        else:
            return JsonResponse({"error": "Credenciales inválidas"}, status=401)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ─────────────────────────────────────────────────────────────
# POST /auth/registro/
# Permite crear un nuevo usuario en la base de datos.
# ─────────────────────────────────────────────────────────────
@csrf_exempt
def registro_usuario(request):
    if request.method != "POST":
        return JsonResponse({"error": "Metodo no permitido"}, status=405)
    try:
        data     = json.loads(request.body)
        email    = data.get("email", "").strip()
        password = data.get("password", "")
        nombre   = data.get("nombre", email.split("@")[0])

        if not email or not password:
            return JsonResponse({"error": "Email y password son obligatorios"}, status=400)

        if len(password) < 8:
            return JsonResponse({"error": "La contraseña debe tener al menos 8 caracteres"}, status=400)

        if User.objects.filter(username=email).exists():
            return JsonResponse({"error": "El usuario ya existe"}, status=409)

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=nombre,
        )

        return JsonResponse({
            "mensaje":  "Usuario creado exitosamente",
            "usuario":  user.username,
            "status":   "success",
        }, status=201)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ─────────────────────────────────────────────────────────────
# GET /auth/perfil/
# Retorna los datos del usuario autenticado.
# Requiere el header: Authorization: Bearer <token>
# ─────────────────────────────────────────────────────────────
@csrf_exempt
def perfil_usuario(request):
    if request.method != "GET":
        return JsonResponse({"error": "Metodo no permitido"}, status=405)

    payload = _verificar_token(request)
    if payload is None:
        return JsonResponse({"error": "Token inválido o expirado"}, status=401)

    try:
        user = User.objects.get(id=payload["user_id"])
        return JsonResponse({
            "usuario":     user.username,
            "email":       user.email,
            "nombre":      user.get_full_name() or user.username,
            "es_staff":    user.is_staff,
            "fecha_ingreso": user.date_joined.isoformat(),
        }, status=200)
    except User.DoesNotExist:
        return JsonResponse({"error": "Usuario no encontrado"}, status=404)


# ─────────────────────────────────────────────────────────────
# POST /auth/logout/
# ─────────────────────────────────────────────────────────────
@csrf_exempt
def logout_usuario(request):
    if request.method != "POST":
        return JsonResponse({"error": "Metodo no permitido"}, status=405)
    logout(request)
    return JsonResponse({"mensaje": "Sesión cerrada correctamente", "status": "success"}, status=200)


# ─────────────────────────────────────────────────────────────
# POST /auth/validar-token/
# Usado internamente por Kong para verificar tokens en cada request.
# Kong llama aquí antes de redirigir al microservicio destino.
# ─────────────────────────────────────────────────────────────
@csrf_exempt
def validar_token(request):
    if request.method != "POST":
        return JsonResponse({"error": "Metodo no permitido"}, status=405)

    payload = _verificar_token(request)
    if payload is None:
        return JsonResponse({"valid": False, "error": "Token inválido o expirado"}, status=401)

    return JsonResponse({
        "valid":    True,
        "usuario":  payload.get("sub"),
        "user_id":  payload.get("user_id"),
        "email":    payload.get("email"),
        "is_staff": payload.get("is_staff"),
        "exp":      payload.get("exp"),
    }, status=200)

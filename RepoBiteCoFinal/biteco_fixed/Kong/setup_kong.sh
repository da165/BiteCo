#!/bin/bash
# =============================================================================
# setup_kong.sh — Configura Kong API Gateway para Bite.Co
# =============================================================================
# Este script registra en Kong:
#   1. Los tres servicios (Seguridad, Base_Datos, AWS)
#   2. Las rutas de cada servicio
#   3. El plugin JWT para proteger Base_Datos y AWS
#   4. El consumer "biteco-client" con su clave JWT
#
# Uso:
#   # En la misma máquina donde corre Kong:
#   chmod +x setup_kong.sh
#   ./setup_kong.sh
#
#   # Apuntando a otra IP:
#   KONG_ADMIN=http://IP_KONG:8001 ./setup_kong.sh
#
# Variables requeridas (ajustar con IPs reales de cada EC2):
#   IP_SEGURIDAD   — IP de la EC2 que corre el microservicio Seguridad
#   IP_BASE_DATOS  — IP de la EC2 que corre el microservicio Base_Datos
#   IP_AWS         — IP de la EC2 que corre el microservicio AWS
# =============================================================================

set -euo pipefail

KONG_ADMIN=${KONG_ADMIN:-"http://localhost:8001"}
IP_SEGURIDAD=${IP_SEGURIDAD:-"seguridad-service"}
IP_BASE_DATOS=${IP_BASE_DATOS:-"basedatos-service"}
IP_AWS=${IP_AWS:-"aws-service"}

PORT_SEGURIDAD=${PORT_SEGURIDAD:-8000}
PORT_BASE_DATOS=${PORT_BASE_DATOS:-8002}
PORT_AWS=${PORT_AWS:-8001}

# Clave secreta JWT — debe coincidir con JWT_SECRET en settings.py de Seguridad
JWT_SECRET=${JWT_SECRET:-"biteco-jwt-secret-sprint2-2025"}

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Configurando Kong API Gateway — Bite.Co Sprint 2   ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Kong Admin API: $KONG_ADMIN"
echo "  Seguridad:      http://$IP_SEGURIDAD:$PORT_SEGURIDAD"
echo "  Base_Datos:     http://$IP_BASE_DATOS:$PORT_BASE_DATOS"
echo "  AWS:            http://$IP_AWS:$PORT_AWS"
echo ""

# Esperar a que Kong esté listo
echo "Esperando a que Kong esté listo..."
until curl -sf "$KONG_ADMIN/status" > /dev/null; do
    echo "  Kong no disponible todavía, reintentando en 5s..."
    sleep 5
done
echo "  Kong listo."
echo ""

# =============================================================================
# SERVICIO 1: Seguridad (sin JWT — es quien genera el token)
# =============================================================================
echo "── Registrando Servicio: Seguridad ──────────────────────"

curl -sf -X PUT "$KONG_ADMIN/services/seguridad-service" \
  -d "name=seguridad-service" \
  -d "url=http://$IP_SEGURIDAD:$PORT_SEGURIDAD" > /dev/null
echo "  Servicio 'seguridad-service' registrado."

# Ruta: /auth/* → Seguridad (sin autenticación — es el punto de login)
curl -sf -X PUT "$KONG_ADMIN/services/seguridad-service/routes/auth-route" \
  -d "name=auth-route" \
  -d "paths[]=/auth" \
  -d "strip_path=false" > /dev/null
echo "  Ruta /auth/* → seguridad-service registrada."

# Plugin CORS para el endpoint de login (frontend puede llamarlo)
curl -sf -X POST "$KONG_ADMIN/services/seguridad-service/plugins" \
  -d "name=cors" \
  -d "config.origins=*" \
  -d "config.methods=GET,POST,OPTIONS" \
  -d "config.headers=Content-Type,Authorization" \
  -d "config.max_age=3600" > /dev/null
echo "  Plugin CORS aplicado a seguridad-service."
echo ""

# =============================================================================
# SERVICIO 2: Base_Datos — PROTEGIDO con JWT
# =============================================================================
echo "── Registrando Servicio: Base_Datos ─────────────────────"

curl -sf -X PUT "$KONG_ADMIN/services/basedatos-service" \
  -d "name=basedatos-service" \
  -d "url=http://$IP_BASE_DATOS:$PORT_BASE_DATOS" > /dev/null
echo "  Servicio 'basedatos-service' registrado."

curl -sf -X PUT "$KONG_ADMIN/services/basedatos-service/routes/reportes-route" \
  -d "name=reportes-route" \
  -d "paths[]=/api/reportes" \
  -d "strip_path=false" > /dev/null
echo "  Ruta /api/reportes/* → basedatos-service registrada."

# Plugin JWT: Kong verifica el token antes de pasar la petición
curl -sf -X POST "$KONG_ADMIN/services/basedatos-service/plugins" \
  -d "name=jwt" \
  -d "config.secret_is_base64=false" \
  -d "config.header_names=Authorization" > /dev/null
echo "  Plugin JWT aplicado a basedatos-service."

# Plugin Rate Limiting adicional a nivel de Kong
curl -sf -X POST "$KONG_ADMIN/services/basedatos-service/plugins" \
  -d "name=rate-limiting" \
  -d "config.minute=300" \
  -d "config.hour=10000" \
  -d "config.policy=redis" \
  -d "config.redis_host=$IP_SEGURIDAD" \
  -d "config.redis_port=6379" > /dev/null
echo "  Plugin rate-limiting aplicado a basedatos-service."
echo ""

# =============================================================================
# SERVICIO 3: AWS — PROTEGIDO con JWT
# =============================================================================
echo "── Registrando Servicio: AWS ────────────────────────────"

curl -sf -X PUT "$KONG_ADMIN/services/aws-service" \
  -d "name=aws-service" \
  -d "url=http://$IP_AWS:$PORT_AWS" > /dev/null
echo "  Servicio 'aws-service' registrado."

curl -sf -X PUT "$KONG_ADMIN/services/aws-service/routes/costos-route" \
  -d "name=costos-route" \
  -d "paths[]=/api/aws" \
  -d "strip_path=false" > /dev/null
echo "  Ruta /api/aws/* → aws-service registrada."

curl -sf -X POST "$KONG_ADMIN/services/aws-service/plugins" \
  -d "name=jwt" \
  -d "config.secret_is_base64=false" \
  -d "config.header_names=Authorization" > /dev/null
echo "  Plugin JWT aplicado a aws-service."
echo ""

# =============================================================================
# CONSUMER: biteco-client con credencial JWT
# =============================================================================
echo "── Creando Consumer y credencial JWT ────────────────────"

# Crear el consumer (representa a todos los clientes autenticados)
curl -sf -X PUT "$KONG_ADMIN/consumers/biteco-client" \
  -d "username=biteco-client" > /dev/null
echo "  Consumer 'biteco-client' creado."

# Crear la credencial JWT con el mismo secret que usa Django para firmar tokens
curl -sf -X POST "$KONG_ADMIN/consumers/biteco-client/jwt" \
  -d "key=biteco-client" \
  -d "secret=$JWT_SECRET" \
  -d "algorithm=HS256" > /dev/null
echo "  Credencial JWT registrada (secret: $JWT_SECRET)."
echo ""

# =============================================================================
# HEALTH CHECK ROUTE (sin JWT — para monitoreo)
# =============================================================================
echo "── Registrando rutas de health check ────────────────────"

curl -sf -X PUT "$KONG_ADMIN/services/seguridad-service/routes/health-seg" \
  -d "name=health-seg" \
  -d "paths[]=/health/seguridad" \
  -d "strip_path=true" > /dev/null
echo "  Ruta /health/seguridad registrada."

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Kong configurado exitosamente                      ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Rutas disponibles en http://IP_KONG:8080           ║"
echo "║                                                      ║"
echo "║  POST /auth/login/          — Sin JWT (login)        ║"
echo "║  POST /auth/registro/       — Sin JWT (registro)     ║"
echo "║  GET  /auth/perfil/         — Sin JWT (perfil)       ║"
echo "║  GET  /api/reportes/*/      — Requiere JWT           ║"
echo "║  GET  /api/aws/costos/*/    — Requiere JWT           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Ejemplo de uso:"
echo "  # 1. Login (obtener token):"
echo "  TOKEN=\$(curl -s -X POST http://IP_KONG:8080/auth/login/ \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"email\":\"financiero@biteco.com\",\"password\":\"Financiero123!\"}' \\"
echo "    | python3 -c \"import sys,json; print(json.load(sys.stdin)['token'])\")"
echo ""
echo "  # 2. Usar el token:"
echo "  curl http://IP_KONG:8080/api/reportes/proyecto-001/2025-01/ \\"
echo "    -H \"Authorization: Bearer \$TOKEN\""

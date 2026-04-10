# Kong API Gateway — Bite.Co

Kong es el punto de entrada único del sistema. Los clientes (frontend, JMeter, Locust) 
**nunca llaman directamente** a los microservicios — siempre pasan por Kong.

## Arquitectura de flujo

```
Cliente
   │
   ▼ puerto 8080
┌─────────────────────────────────────┐
│           KONG API GATEWAY          │
│                                     │
│  /auth/*   ──────────────────────── │──► EC2-Seguridad :8000
│  (sin JWT)                          │    POST /auth/login/  → genera JWT
│                                     │    POST /auth/registro/
│  /api/reportes/*  ─── JWT check ─── │──► EC2-BaseDatos :8002
│  /api/aws/*       ─── JWT check ─── │──► EC2-AWS       :8001
└─────────────────────────────────────┘
```

## Flujo completo de autenticación

```
1. Cliente → POST /auth/login/  → Kong → Seguridad
2. Seguridad valida credenciales en PostgreSQL (auth_user)
3. Seguridad retorna JWT firmado con JWT_SECRET
4. Cliente guarda el JWT

5. Cliente → GET /api/reportes/... + header: Authorization: Bearer TOKEN
6. Kong intercepta, verifica el JWT (misma clave JWT_SECRET)
7. Si válido: Kong añade header X-Kong-Consumer-Username y reenvía a Base_Datos
8. Base_Datos procesa sin volver a validar (confía en Kong)
```

## Despliegue

### Opción A: Kong en la misma EC2 que Seguridad

```bash
# En EC2-Seguridad:
cd ~/Bite_co/Kong
docker compose -f docker-compose.kong.yml up -d

# Esperar ~30 segundos a que Kong inicie, luego configurar:
IP_SEGURIDAD=127.0.0.1 \
IP_BASE_DATOS=IP_PRIVADA_EC2_BASE_DATOS \
IP_AWS=IP_PRIVADA_EC2_AWS \
./setup_kong.sh
```

### Opción B: Kong en EC2 propia (recomendado para carga alta)

```bash
# En una EC2 nueva dedicada a Kong:
cd ~/Bite_co/Kong
docker compose -f docker-compose.kong.yml up -d

IP_SEGURIDAD=IP_PRIVADA_EC2_SEGURIDAD \
IP_BASE_DATOS=IP_PRIVADA_EC2_BASE_DATOS \
IP_AWS=IP_PRIVADA_EC2_AWS \
KONG_ADMIN=http://localhost:8001 \
./setup_kong.sh
```

## Puertos

| Puerto | Uso                                      |
|--------|------------------------------------------|
| 8080   | Proxy (clientes llaman aquí)             |
| 8001   | Admin API de Kong (configuración)        |
| 1337   | Konga UI (panel visual de Kong)          |

## Verificar que Kong funciona

```bash
# Verificar estado de Kong:
curl http://localhost:8001/status

# Ver servicios registrados:
curl http://localhost:8001/services

# Ver rutas registradas:
curl http://localhost:8001/routes

# Ver plugins activos:
curl http://localhost:8001/plugins
```

## Prueba completa del flujo

```bash
KONG_HOST=http://IP_KONG:8080

# 1. Registrar usuario:
curl -X POST $KONG_HOST/auth/registro/ \
  -H "Content-Type: application/json" \
  -d '{"email":"nuevo@biteco.com","password":"MiPass123!"}'

# 2. Login → obtener token:
TOKEN=$(curl -s -X POST $KONG_HOST/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"financiero@biteco.com","password":"Financiero123!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

echo "Token: $TOKEN"

# 3. Acceder a un reporte CON el token:
curl $KONG_HOST/api/reportes/proyecto-001/2025-01/ \
  -H "Authorization: Bearer $TOKEN"

# 4. Intentar sin token (debe dar 401):
curl $KONG_HOST/api/reportes/proyecto-001/2025-01/
# → {"message":"Unauthorized"}
```

## Acceso a Konga (panel visual)

1. Abre http://IP_KONG:1337 en el navegador
2. Crea una cuenta de administrador en Konga
3. Conecta Konga a Kong: Connection URL = http://kong:8001
4. Desde Konga puedes ver y editar servicios, rutas y plugins gráficamente

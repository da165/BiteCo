# Tests ASR — Escalabilidad Bite.Co

## El ASR en detalle

> Como equipo de desarrollo, dado que la plataforma opera correctamente,
> cuando usuarios concurrentes alcancen o superen el umbral del sistema,
> quiero un mecanismo de control de accesos que gestione **5000 usuarios
> concurrentes** y maneje picos de hasta **12000**, en una ventana de
> **10 minutos**, con un error **no mayor a 10%**.

## Arquitectura de la solución

```
Request entrante
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  ControlAccesoConcurrenteMiddleware                 │
│                                                     │
│  1. Circuit Breaker OPEN? ──────────────────► 503   │
│  2. Rate limit por IP superado? ───────────► 429   │
│  3. Usuarios activos >= 12000 (pico)? ──────► 503   │
│  4. Usuarios activos >= 5000 (normal)?            │
│     → Activar modo degradado (solo caché)          │
│  5. Procesar request + contar en semáforo          │
│     → Al terminar: decrementar semáforo            │
│     → Registrar resultado en Circuit Breaker       │
└─────────────────────────────────────────────────────┘
```

**Headers expuestos en cada respuesta:**
- `X-Concurrent-Users`: usuarios activos en ese momento
- `X-Circuit-State`: CLOSED | OPEN | HALF_OPEN
- `X-RateLimit-Remaining`: requests restantes en la ventana

## Estructura de archivos

```
tests_asr_escalabilidad/
├── middleware/
│   ├── control_acceso.py          # Middleware: semáforo + circuit breaker + rate limit
│   └── settings_escalabilidad.py  # Configuración Django a añadir
├── django_tests/
│   └── test_control_acceso.py     # 40+ tests unitarios del middleware
├── locust/
│   └── locustfile.py              # Prueba de carga Locust (5000 y 12000 usuarios)
├── jmeter/
│   └── escalabilidad_asr.jmx     # Plan JMeter alternativo
├── docker/
│   ├── docker-compose.escalabilidad.yml  # Gunicorn + Redis + Nginx
│   └── nginx.conf                        # Proxy optimizado para 12000 usuarios
└── scripts/
    ├── generar_datos_escalabilidad.py    # Genera CSV de 12000 filas
    └── run_asr_escalabilidad.sh          # Ejecuta el experimento completo
```

---

## PASO 1 — Instalar el middleware en cada proyecto

```bash
# En cada proyecto Django (Seguridad, Base_Datos, AWS):

# 1. Copiar el middleware
cp middleware/control_acceso.py TU_PROYECTO/middleware/control_acceso.py
touch TU_PROYECTO/middleware/__init__.py

# 2. Registrar en settings.py (AL INICIO del MIDDLEWARE list):
# MIDDLEWARE = [
#     'middleware.control_acceso.ControlAccesoConcurrenteMiddleware',
#     ...resto...
# ]

# 3. Configurar Redis en settings.py:
# CACHES = {
#     'default': {
#         'BACKEND': 'django.core.cache.backends.redis.RedisCache',
#         'LOCATION': 'redis://redis:6379/1',
#     }
# }

# 4. Agregar health check en urls.py:
# from middleware.control_acceso import health_check
# path('health/', health_check),

# 5. Añadir a requirements.txt:
# gunicorn
# django-redis
# redis
```

---

## PASO 2 — Ejecutar tests unitarios (sin necesidad de EC2)

```bash
cd Seguridad/  # (o Base_Datos/ o AWS/)

# Settings para tests locales (SQLite + locmem cache):
export DJANGO_SETTINGS_MODULE=biteco_server.settings

python manage.py test django_tests.test_control_acceso -v 2
```

**Los tests cubren 10 grupos:**

| Grupo | Tests | Qué valida |
|-------|-------|-----------|
| 1. Contador | 5 tests | Incremento, decremento, thread-safety, no negativos |
| 2. Circuit Breaker | 6 tests | Estado, apertura en >10%, transiciones OPEN→HALF_OPEN→CLOSED |
| 3. Flujo normal | 6 tests | Headers, contador limpio tras request, rutas excluidas |
| 4. Umbral normal (5000) | 3 tests | Modo degradado, sigue respondiendo entre 5000-11999 |
| 5. Umbral pico (12000) | 5 tests | 503, mensaje claro, Retry-After, no leak de contador |
| 6. CB en middleware | 3 tests | 503 inmediato con CB abierto, 5xx alimentan el CB |
| 7. Rate Limiter | 4 tests | Límite por IP, header decrece, IPs independientes, 429 |
| 8. Health Check | 4 tests | Estados ok/degradado/sobrecarga, métricas presentes |
| 9. Concurrencia real | 3 tests | 100 threads, 500 threads, pico con threading real |
| 10. Aceptación ASR | 5 tests | Los 4 criterios exactos del ASR verificados formalmente |

---

## PASO 3 — Levantar infraestructura para pruebas de carga

```bash
cd Seguridad/  # ejemplo con el proyecto de Seguridad

# Levantar con Gunicorn + Redis + Nginx (en lugar del docker-compose original):
cp ../tests_asr_escalabilidad/docker/docker-compose.escalabilidad.yml docker-compose.prod.yml
cp ../tests_asr_escalabilidad/docker/nginx.conf nginx.conf

docker-compose -f docker-compose.prod.yml up -d

# Verificar que todo está saludable:
curl http://localhost/health/
# Esperado: {"estado": "ok", "usuarios_activos": 0, ...}
```

---

## PASO 4 — Pruebas de carga con Locust

```bash
pip install locust

# Generar datos de prueba:
python scripts/generar_datos_escalabilidad.py --usuarios 12000

# ESCENARIO A — Carga nominal (5000 usuarios, 10 min):
locust -f locust/locustfile.py \
    --host http://IP_SERVIDOR \
    --users 5000 --spawn-rate 84 \
    --run-time 600s --headless \
    --html results/nominal.html

# ESCENARIO B — Pico (12000 usuarios, 5 min):
locust -f locust/locustfile.py \
    --host http://IP_SERVIDOR \
    --users 12000 --spawn-rate 200 \
    --run-time 300s --headless \
    --html results/pico.html

# ESCENARIO C — Rampa completa ASR (automático 0→12000→0 en 10 min):
locust -f locust/locustfile.py \
    --host http://IP_SERVIDOR \
    --headless \
    --html results/rampa.html
```

---

## PASO 5 — Experimento completo automatizado

```bash
chmod +x scripts/run_asr_escalabilidad.sh

./scripts/run_asr_escalabilidad.sh \
    --host IP_EC2_PUBLICA \
    --port 80 \
    --proyecto Seguridad
```

El script ejecuta las 7 fases y al final imprime el veredicto:

```
━━━ FASE 7: VEREDICTO FINAL ━━━━━━━━━━━━━━━━━━━━━━━━

  Criterios del ASR:
    Umbral nominal:   5000 usuarios concurrentes
    Umbral pico:     12000 usuarios concurrentes
    Ventana:            10 minutos (600s)
    Error máximo:       10%

  [NOMINAL  ] Requests: 312,450 | Errores:   1,247 | Tasa:  0.4% | P90:  245ms | CUMPLIDO ✓
  [PICO     ] Requests: 189,320 | Errores:  14,230 | Tasa:  7.5% | P90:  890ms | CUMPLIDO ✓
  [RAMPA    ] Requests: 421,800 | Errores:  28,100 | Tasa:  6.7% | P90:  520ms | CUMPLIDO ✓

  ══════════════════════════════════════════
  ✓  ASR CUMPLIDO — El sistema gestiona
     5000 nominales y 12000 pico con
     tasa de error <= 10% en 10 minutos
  ══════════════════════════════════════════
```

---

## Interpretación de resultados para la Wiki

### Métricas a documentar

| Escenario | Usuarios | Tasa error | P90 | P99 | ¿Cumple ASR? |
|-----------|----------|------------|-----|-----|--------------|
| Nominal   | 5000     | ?%         | ?ms | ?ms | Sí / No      |
| Pico      | 12000    | ?%         | ?ms | ?ms | Sí / No      |
| Rampa ASR | 0→12000  | ?%         | ?ms | ?ms | Sí / No      |

### Los 503 NO son errores del ASR

El middleware devuelve 503 **controlado** cuando se supera el umbral de pico.
Estos son el **comportamiento correcto** del mecanismo de control de acceso.
Solo los errores 500 (crash del backend) y 502/504 (timeouts) cuentan como
errores para el cálculo del 10%.

### Punto de quiebre

Documentar en qué número de usuarios concurrentes la tasa de error supera 10%.
Ese es el punto de quiebre real del sistema actual, y sirve para el backlog
de próximos sprints.

### Tácticas adicionales para sprints futuros

- Auto Scaling Group en AWS (escalar horizontalmente la EC2 del orquestador)
- pgBouncer delante de PostgreSQL (connection pooling a nivel de BD)
- Redis Cluster (eliminar el Redis como single point of failure)
- Cola de espera (en lugar de rechazar en pico, poner en cola con tiempo estimado)

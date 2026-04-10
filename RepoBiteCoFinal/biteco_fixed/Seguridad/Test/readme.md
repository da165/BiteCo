# 🧪 Guía de Tests — Sprint 2 Bite.Co
**ASR:** Latencia < 100ms en generación de reportes financieros con Microservicios

---

## Estructura de archivos

```
tests/
├── seguridad/
│   └── test_login.py          # Tests unitarios del microservicio Seguridad
├── aws/
│   └── test_costos_aws.py     # Tests unitarios del microservicio AWS (boto3 mockeado)
├── base_datos/
│   └── test_reporte.py        # Tests unitarios del Orquestador (cache, BD, AWS fallback)
├── latencia/
│   ├── test_latencia_asr.py   # Script Python que mide latencia Prueba A vs B
│   └── plan_prueba_experimento.jmx  # Plan de carga JMeter
└── setup_y_tests_ec2.sh       # Script todo-en-uno para EC2
```

---

## PASO 1 — Copiar los tests a cada microservicio en EC2

### Microservicio Seguridad
```bash
# Desde tu máquina local:
scp tests/seguridad/test_login.py ubuntu@<IP_SEGURIDAD>:~/Seguridad/seguridad/tests.py
```

### Microservicio AWS
```bash
scp tests/aws/test_costos_aws.py ubuntu@<IP_AWS>:~/AWS/AWS_Consulta/tests.py
```

### Microservicio Base_Datos (Orquestador)
```bash
scp tests/base_datos/test_reporte.py ubuntu@<IP_BD>:~/Base_Datos/BD_ManejoCostos/tests.py
```

---

## PASO 2 — Correr Tests Unitarios (en cada EC2)

```bash
# En la EC2 del microservicio Seguridad:
cd ~/Seguridad
python manage.py test seguridad --verbosity=2

# En la EC2 del microservicio AWS:
cd ~/AWS
python manage.py test AWS_Consulta --verbosity=2

# En la EC2 del Orquestador Base_Datos:
cd ~/Base_Datos
python manage.py test BD_ManejoCostos --verbosity=2
```

**Resultado esperado:** todos los tests en verde (OK).

---

## PASO 3 — Correr Tests de Latencia ASR con Python

```bash
# Instalar dependencias
pip3 install requests tabulate

# Correr el experimento (Prueba A vs Prueba B)
python3 tests/latencia/test_latencia_asr.py \
    --host-secuencial http://<IP_EC2_ORQUESTADOR>:8002 \
    --host-broker     http://<IP_EC2_ORQUESTADOR_BROKER>:8003 \
    --usuarios 1 10 50 100 200 500
```

Genera tabla como:

```
+──────────────+──────────+───────────────+──────────+──────────+──────────+───────────+──────────────+
| Modo         | Usuarios | Promedio (ms) | P95 (ms) | P99 (ms) | Max (ms) | Errores % | ASR <100ms   |
+──────────────+──────────+───────────────+──────────+──────────+──────────+───────────+──────────────+
| Secuencial   |        1 | 62.34         | 70.12    | 80.00    | 85.00    | 0.0%      | ✅ SÍ        |
| Con Broker   |        1 | 28.11         | 35.00    | 40.00    | 45.00    | 0.0%      | ✅ SÍ        |
| Secuencial   |      500 | 450.23        | 800.00   | 950.00   | 1200.00  | 5.0%      | ❌ NO        |
| Con Broker   |      500 | 95.12         | 98.00    | 99.00    | 105.00   | 0.5%      | ✅ SÍ        |
+──────────────+──────────+───────────────+──────────+──────────+──────────+───────────+──────────────+
```

---

## PASO 4 — Correr Tests JMeter (headless en EC2)

```bash
# Instalar JMeter (si no está instalado)
./setup_y_tests_ec2.sh instalar

# Correr el plan .jmx
/opt/jmeter/bin/jmeter \
    -n \
    -t tests/latencia/plan_prueba_experimento.jmx \
    -l resultados.jtl \
    -e -o reporte_html/ \
    -JHOST_ORQUESTADOR=<IP_EC2> \
    -JPUERTO_ORQUESTADOR=8002

# Copiar reporte a máquina local para visualizar
scp -r ubuntu@<IP_EC2>:~/reporte_html/ ./reporte_jmeter_local/
```

Abre `reporte_jmeter_local/index.html` en tu navegador.

---

## PASO 5 — Script todo-en-uno EC2

```bash
chmod +x setup_y_tests_ec2.sh

# Correr todo:
./setup_y_tests_ec2.sh todo

# Solo unitarios:
./setup_y_tests_ec2.sh unitarios

# Solo latencia python:
./setup_y_tests_ec2.sh latencia

# Solo JMeter:
./setup_y_tests_ec2.sh jmeter
```

---

## Escenarios cubiertos por los tests

| Microservicio | Escenario | Resultado esperado |
|---|---|---|
| Seguridad | Login con credenciales válidas | HTTP 200, status=success |
| Seguridad | Password incorrecta | HTTP 401 |
| Seguridad | Usuario no existe | HTTP 401 |
| Seguridad | Método GET | HTTP 405 |
| Seguridad | Body malformado (no JSON) | HTTP 400 |
| AWS | Consulta exitosa a Cost Explorer | HTTP 200, campos completos |
| AWS | ClientError de AWS | HTTP 500 |
| AWS | Diferentes project_ids en URL | HTTP 200 con project_id correcto |
| Base_Datos | Cache HIT | HTTP 200, origen='cache' |
| Base_Datos | BD HIT (cache miss) | HTTP 200, origen='base_de_datos' |
| Base_Datos | AWS fallback (BD miss) | HTTP 200, origen='microservicio_aws' |
| Base_Datos | AWS falla (status != 200) | HTTP 404 |
| Base_Datos | Conexión AWS caída | HTTP 503 |
| Base_Datos | Segunda llamada usa caché | No llama a AWS de nuevo |
| Latencia | 1 usuario, modo secuencial | < 100ms ✅ |
| Latencia | 500 usuarios, modo secuencial | Probable quiebre > 100ms |
| Latencia | 500 usuarios, con Broker | Debe mantenerse < 100ms ✅ |

---

## Variables de entorno útiles

```bash
export HOST_ORQUESTADOR="http://54.123.45.67:8002"
export HOST_BROKER="http://54.123.45.68:8003"
```

---

## Notas importantes

1. **Los tests unitarios NO necesitan EC2 ni AWS reales**: todo está mockeado con `unittest.mock`.
2. **Los tests de latencia SÍ necesitan** que los microservicios estén corriendo en EC2.
3. **El plan JMeter** debe ajustar las IPs en la sección "Variables Globales" antes de correr.
4. **La caché** en Base_Datos usa `django.core.cache` — en tests usa LocMemCache (en memoria), en producción debes configurar Redis.

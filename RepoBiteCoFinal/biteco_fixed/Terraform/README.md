# Terraform — Bite.Co Sprint 2

Despliega toda la infraestructura en **un solo comando**.

## Arquitectura desplegada

```
                    ┌─────────────────────────────────┐
                    │   EC2-Kong  (API Gateway)        │
                    │   Kong :8080  Konga :1337        │
                    └───────────┬─────────────────────┘
                                │ valida JWT y rutea
          ┌─────────────────────┼─────────────────┐
          ▼                     ▼                  ▼
  EC2-Seguridad          EC2-BaseDatos         EC2-AWS
  Django Auth            Django Orq.           Django Cost
  Gunicorn+Redis         Gunicorn+Redis        Gunicorn+Redis
  :8000                  :8000                 :8000
          │                     │
          └──────────┬──────────┘
                     ▼
              EC2-BD-Postgres
              PostgreSQL :5432
              (usuariosbitecodb + bitecodb)

  EC2-Pruebas — JMeter + Locust (separada del tráfico productivo)
```

## Prerrequisitos

```bash
# 1. Instalar Terraform (en tu máquina local)
# Mac:
brew install terraform

# Linux:
sudo apt-get install -y gnupg software-properties-common
wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | \
  sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
  https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
  sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt-get install terraform

# Windows: descargar desde https://developer.hashicorp.com/terraform/downloads
```

## Despliegue paso a paso

### Paso 1 — Generar el par de claves SSH

```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/biteco-sprint2-key -N ""
# Esto crea dos archivos:
#   ~/.ssh/biteco-sprint2-key      (clave privada — NUNCA compartir)
#   ~/.ssh/biteco-sprint2-key.pub  (clave pública — la que va a AWS)
```

### Paso 2 — Configurar credenciales del Lab de AWS Academy

En el panel del Lab, haz clic en "AWS Details" y copia las credenciales en tu terminal:

```bash
export AWS_ACCESS_KEY_ID="ASIA..."
export AWS_SECRET_ACCESS_KEY="xxxx..."
export AWS_SESSION_TOKEN="FwoG..."
```

### Paso 3 — Editar terraform.tfvars

Abre `terraform.tfvars` y cambia:
- `repo_url` — URL de tu repositorio en Azure DevOps

### Paso 4 — Inicializar y aplicar

```bash
cd Terraform/
terraform init
terraform plan    # revisa lo que se va a crear
terraform apply   # escribe 'yes' cuando pregunte
```

El proceso tarda ~4 minutos. Al final verás las IPs de todas las instancias.

### Paso 5 — Esperar a que los servicios arranquen

Los scripts `user_data` se ejecutan en segundo plano. Espera **5-8 minutos** después de que `terraform apply` termine antes de probar los endpoints.

Puedes monitorear el progreso:
```bash
ssh -i ~/.ssh/biteco-sprint2-key ubuntu@IP_SEGURIDAD
sudo tail -f /var/log/user-data.log
```

### Paso 6 — Verificar

```bash
KONG=http://IP_KONG:8080

# Health check:
curl $KONG/auth/health/   # no existe — usa el directo:
curl http://IP_SEGURIDAD:8000/health/

# Login y obtener token:
TOKEN=$(curl -s -X POST $KONG/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"financiero@biteco.com","password":"Financiero123!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
echo $TOKEN

# Consultar reporte (con JWT):
curl $KONG/api/reportes/proyecto-001/2025-01/ \
  -H "Authorization: Bearer $TOKEN"
```

## Destruir la infraestructura

```bash
terraform destroy   # escribe 'yes' para confirmar
```

Esto elimina TODAS las instancias y recursos. Los datos en PostgreSQL se perderán.

## Nota sobre AWS Academy

Las credenciales del Lab expiran cada sesión. Cuando reanuudes el Lab:
1. Copia las nuevas credenciales (`AWS Details`)
2. Exporta como variables de entorno
3. Las instancias EC2 siguen existiendo — solo vuelve a arrancarlas desde la consola si estaban detenidas

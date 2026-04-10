# =============================================================================
# terraform.tfvars — EDITA ESTE ARCHIVO antes de ejecutar terraform apply
# =============================================================================
# Pasos obligatorios:
#   1. Cambia repo_url por la URL real de tu repositorio en Azure DevOps
#   2. Cambia las contraseñas por valores seguros
#   3. Ajusta public_key_path a la ruta de tu clave .pub
#      Mac/Linux:  "/home/TU_USUARIO/.ssh/biteco-sprint2-key.pub"
#      Windows:    "C:/Users/TU_USUARIO/.ssh/biteco-sprint2-key.pub"
# =============================================================================

# URL del repositorio en Azure DevOps (OBLIGATORIO — cambia esto)
repo_url = "https://TU-ORG@dev.azure.com/TU-ORG/TU-PROYECTO/_git/Bite_co"

# Tipo de instancia
instance_type_app     = "t3.medium"
instance_type_pruebas = "t3.large"

# Key pair SSH
key_name        = "biteco-sprint2-key"
# CAMBIA la ruta según tu sistema operativo y usuario:
public_key_path = "/home/TU_USUARIO/.ssh/biteco-sprint2-key.pub"

# Región (no cambiar en AWS Academy)
aws_region = "us-east-1"

# Secretos — CAMBIA estos valores por unos más seguros
jwt_secret            = "biteco-jwt-secret-CAMBIA-ESTO-2025"
db_password_seguridad = "Seguridad123!"
db_password_basedatos = "BaseDatos123!"

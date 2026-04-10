# =============================================================================
# variables.tf — Parámetros configurables del despliegue Bite.Co
# =============================================================================

variable "aws_region" {
  description = "Región AWS donde se crean los recursos (debe ser us-east-1 en Academy)"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Prefijo de nombre para todos los recursos creados"
  type        = string
  default     = "biteco"
}

variable "key_name" {
  description = "Nombre del key pair en AWS"
  type        = string
  default     = "biteco-sprint2-key"
}

variable "public_key_path" {
  description = "Ruta al archivo .pub de tu llave SSH local"
  type        = string
  default     = "~/.ssh/biteco-sprint2-key.pub"
}

variable "instance_type_app" {
  description = "Tipo de instancia para microservicios (ASR: mínimo t3.medium para Gunicorn 9 workers)"
  type        = string
  default     = "t3.medium"
}

variable "instance_type_pruebas" {
  description = "Tipo de instancia para la máquina de pruebas de carga (necesita más CPU)"
  type        = string
  default     = "t3.large"
}

variable "repo_url" {
  description = "URL HTTPS del repositorio en Azure DevOps"
  type        = string
  # Ejemplo: "https://TU-ORG@dev.azure.com/TU-ORG/TU-PROYECTO/_git/Bite_co"
}

variable "jwt_secret" {
  description = "Clave secreta para firmar y verificar tokens JWT (debe ser la misma en todos los servicios)"
  type        = string
  sensitive   = true
  default     = "biteco-jwt-secret-sprint2-2025"
}

variable "db_password_seguridad" {
  description = "Contraseña de PostgreSQL para la base de datos de Seguridad (usuariosbitecodb)"
  type        = string
  sensitive   = true
  default     = "Seguridad123!"
}

variable "db_password_basedatos" {
  description = "Contraseña de PostgreSQL para la base de datos de Base_Datos (bitecodb)"
  type        = string
  sensitive   = true
  default     = "BaseDatos123!"
}

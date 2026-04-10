# =============================================================================
# outputs.tf — IPs y URLs de todos los servicios desplegados
# Estas salidas aparecen en pantalla al ejecutar terraform apply
# =============================================================================

output "ip_seguridad_publica" {
  description = "IP pública de EC2-Seguridad"
  value       = module.ec2_seguridad.public_ip
}

output "ip_aws_publica" {
  description = "IP pública de EC2-AWS"
  value       = module.ec2_aws.public_ip
}

output "ip_basedatos_publica" {
  description = "IP pública de EC2-Base_Datos"
  value       = module.ec2_basedatos.public_ip
}

output "ip_postgres_publica" {
  description = "IP pública de EC2-BD-Postgres"
  value       = module.ec2_bd_postgres.public_ip
}

output "ip_kong_publica" {
  description = "IP pública de EC2-Kong"
  value       = module.ec2_kong.public_ip
}

output "ip_pruebas_publica" {
  description = "IP pública de EC2-Pruebas"
  value       = module.ec2_pruebas.public_ip
}

output "urls_de_acceso" {
  description = "URLs de acceso a todos los servicios"
  value = {
    kong_proxy     = "http://${module.ec2_kong.public_ip}:8080"
    kong_admin     = "http://${module.ec2_kong.public_ip}:8001"
    konga_ui       = "http://${module.ec2_kong.public_ip}:1337"
    login          = "http://${module.ec2_kong.public_ip}:8080/auth/login/"
    reportes       = "http://${module.ec2_kong.public_ip}:8080/api/reportes/{project}/{mes}/"
    costos_aws     = "http://${module.ec2_kong.public_ip}:8080/api/aws/costos/{project}/"
    health_seg     = "http://${module.ec2_seguridad.public_ip}:8000/health/"
    health_aws     = "http://${module.ec2_aws.public_ip}:8000/health/"
    health_bd      = "http://${module.ec2_basedatos.public_ip}:8000/health/"
    locust_ui      = "http://${module.ec2_pruebas.public_ip}:8089"
  }
}

output "comando_ssh_seguridad" {
  description = "Comando SSH para conectarte a EC2-Seguridad"
  value       = "ssh -i ~/.ssh/biteco-sprint2-key ubuntu@${module.ec2_seguridad.public_ip}"
}

output "comando_ssh_kong" {
  description = "Comando SSH para conectarte a EC2-Kong"
  value       = "ssh -i ~/.ssh/biteco-sprint2-key ubuntu@${module.ec2_kong.public_ip}"
}

output "comando_ssh_pruebas" {
  description = "Comando SSH para conectarte a EC2-Pruebas"
  value       = "ssh -i ~/.ssh/biteco-sprint2-key ubuntu@${module.ec2_pruebas.public_ip}"
}

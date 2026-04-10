# =============================================================================
# Terraform — Bite.Co Sprint 2
# Despliegue completo: 6 EC2 + Security Group + Key Pair
#
# ASR 1: Latencia < 100ms  → Microservicios en EC2 separadas, Gunicorn + Redis
# ASR 2: 5000/12000 users  → t3.medium con 9 workers × 4 threads por servicio
#
# Instancias creadas:
#   ec2_seguridad   — Django Auth + JWT + Kong
#   ec2_aws         — Django AWS Cost Explorer
#   ec2_basedatos   — Django Orquestador (caché→BD→AWS)
#   ec2_bd_postgres — PostgreSQL compartido
#   ec2_kong        — Kong API Gateway + Konga UI
#   ec2_pruebas     — JMeter + Locust (máquina de carga)
# =============================================================================

terraform {
  required_version = ">= 1.3.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
  # En AWS Academy las credenciales vienen del entorno (LabRole).
  # NO pongas access_key / secret_key aquí — se toman de las variables
  # de entorno AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN
  # que copias desde el panel del Lab (botón "AWS Details").
}

# ─── Data: AMI Ubuntu 24.04 más reciente ──────────────────────
data "aws_ami" "ubuntu_24" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ─── Data: VPC por defecto del Lab ────────────────────────────
data "aws_vpc" "default" {
  default = true
}

# ─── Key Pair ─────────────────────────────────────────────────
resource "aws_key_pair" "biteco" {
  key_name   = var.key_name
  public_key = file(var.public_key_path)

  tags = { Name = "biteco-sprint2-key" }
}

# ─── Security Group ───────────────────────────────────────────
module "security_group" {
  source  = "./modules/sg"
  vpc_id  = data.aws_vpc.default.id
  project = var.project
}

# ─── EC2: Seguridad (Auth + Kong en la misma máquina) ─────────
module "ec2_seguridad" {
  source            = "./modules/ec2"
  name              = "seguridad"
  ami               = data.aws_ami.ubuntu_24.id
  instance_type     = var.instance_type_app
  key_name          = aws_key_pair.biteco.key_name
  security_group_id = module.security_group.sg_id
  project           = var.project
  user_data         = templatefile("${path.module}/scripts/user_data_seguridad.sh", {
    repo_url        = var.repo_url
    jwt_secret      = var.jwt_secret
    db_password     = var.db_password_seguridad
    ip_bd_postgres  = module.ec2_bd_postgres.private_ip
  })
}

# ─── EC2: AWS Cost Explorer ───────────────────────────────────
module "ec2_aws" {
  source            = "./modules/ec2"
  name              = "aws-consulta"
  ami               = data.aws_ami.ubuntu_24.id
  instance_type     = var.instance_type_app
  key_name          = aws_key_pair.biteco.key_name
  security_group_id = module.security_group.sg_id
  project           = var.project
  user_data         = templatefile("${path.module}/scripts/user_data_aws.sh", {
    repo_url   = var.repo_url
    jwt_secret = var.jwt_secret
  })
}

# ─── EC2: Base_Datos (Orquestador) ────────────────────────────
module "ec2_basedatos" {
  source            = "./modules/ec2"
  name              = "basedatos"
  ami               = data.aws_ami.ubuntu_24.id
  instance_type     = var.instance_type_app
  key_name          = aws_key_pair.biteco.key_name
  security_group_id = module.security_group.sg_id
  project           = var.project
  user_data         = templatefile("${path.module}/scripts/user_data_basedatos.sh", {
    repo_url        = var.repo_url
    jwt_secret      = var.jwt_secret
    db_password     = var.db_password_basedatos
    ip_bd_postgres  = module.ec2_bd_postgres.private_ip
    ip_aws_service  = module.ec2_aws.private_ip
  })
}

# ─── EC2: PostgreSQL compartido ───────────────────────────────
module "ec2_bd_postgres" {
  source            = "./modules/ec2"
  name              = "bd-postgres"
  ami               = data.aws_ami.ubuntu_24.id
  instance_type     = var.instance_type_app
  key_name          = aws_key_pair.biteco.key_name
  security_group_id = module.security_group.sg_id
  project           = var.project
  user_data         = templatefile("${path.module}/scripts/user_data_postgres.sh", {
    db_password_seguridad = var.db_password_seguridad
    db_password_basedatos = var.db_password_basedatos
  })
}

# ─── EC2: Kong API Gateway ────────────────────────────────────
module "ec2_kong" {
  source            = "./modules/ec2"
  name              = "kong"
  ami               = data.aws_ami.ubuntu_24.id
  instance_type     = var.instance_type_app
  key_name          = aws_key_pair.biteco.key_name
  security_group_id = module.security_group.sg_id
  project           = var.project
  user_data         = templatefile("${path.module}/scripts/user_data_kong.sh", {
    repo_url          = var.repo_url
    jwt_secret        = var.jwt_secret
    ip_seguridad      = module.ec2_seguridad.private_ip
    ip_basedatos      = module.ec2_basedatos.private_ip
    ip_aws            = module.ec2_aws.private_ip
  })
}

# ─── EC2: Pruebas (JMeter + Locust) ───────────────────────────
module "ec2_pruebas" {
  source            = "./modules/ec2"
  name              = "pruebas"
  ami               = data.aws_ami.ubuntu_24.id
  instance_type     = var.instance_type_pruebas
  key_name          = aws_key_pair.biteco.key_name
  security_group_id = module.security_group.sg_id
  project           = var.project
  user_data         = templatefile("${path.module}/scripts/user_data_pruebas.sh", {
    repo_url     = var.repo_url
    ip_kong      = module.ec2_kong.private_ip
    ip_seguridad = module.ec2_seguridad.private_ip
    ip_basedatos = module.ec2_basedatos.private_ip
    ip_aws       = module.ec2_aws.private_ip
    JMETER_VER   ="5.5"
  })
}

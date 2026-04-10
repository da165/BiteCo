# modules/ec2/main.tf
# Módulo reutilizable para crear instancias EC2 con configuración uniforme 

variable "name" {
  type = string
}

variable "ami" {
  type = string
}

variable "instance_type" {
  type = string
}

variable "key_name" {
  type = string
}

variable "security_group_id" {
  type = string
}

variable "project" {
  type = string
}

variable "user_data" {
  type    = string
  default = "" [cite: 254]
}

resource "aws_instance" "this" {
  ami                         = var.ami 
  instance_type               = var.instance_type 
  key_name                    = var.key_name 
  vpc_security_group_ids      = [var.security_group_id] 
  associate_public_ip_address = true 

  # Volumen raíz: 20 GB gp3 (suficiente para Docker images) [cite: 255]
  root_block_device {
    volume_type           = "gp3" [cite: 255]
    volume_size           = 20 [cite: 255]
    delete_on_termination = true [cite: 255]
  }

  user_data = var.user_data 

  tags = {
    Name    = "${var.project}-${var.name}" 
    Project = var.project 
    Sprint  = "2" 
  }
}

output "public_ip" {
  value = aws_instance.this.public_ip 
}

output "private_ip" {
  value = aws_instance.this.private_ip 
}

output "id" {
  value = aws_instance.this.id 
}

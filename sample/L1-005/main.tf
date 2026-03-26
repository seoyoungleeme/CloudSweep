terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

resource "aws_lb" "lb-4dzo8v" {
  name               = "lb-4dzo8v"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.lb-4dzo8v_sg.id]
  subnets = var.public_subnet_ids

  tags = {
    Name = "lb-4dzo8v"
  }
}

resource "aws_lb" "lb-ucc4pu" {
  name               = "lb-ucc4pu"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.lb-ucc4pu_sg.id]
  subnets = var.public_subnet_ids

  tags = {
    Name = "lb-ucc4pu"
  }
}

resource "aws_lb" "lb-ffxzco" {
  name               = "lb-ffxzco"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.lb-ffxzco_sg.id]
  subnets = var.public_subnet_ids

  tags = {
    Name = "lb-ffxzco"
  }
}


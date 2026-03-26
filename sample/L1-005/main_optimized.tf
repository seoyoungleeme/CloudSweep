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

# ──────────────────────────────────────────────
# 삭제 대상 ALB — lb-4dzo8v
# 삭제 전 반드시 아래 검증 완료:
#   1. aws elbv2 describe-load-balancers --names lb-4dzo8v \
#        --query 'LoadBalancers[*].DNSName'
#      → Route53 및 외부 DNS에서 참조 여부 확인
#   2. aws elbv2 describe-listeners --load-balancer-arn <ARN>
#      → 결과 비어 있어야 삭제 가능
#   3. terraform plan -out=cleanup.plan && terraform apply cleanup.plan
#
# 제거 이유: 30일간 request_count = 0, active_connection_count = 0
#            $16.43/월 ALB 고정 비용 낭비 (findings.json 기준)
# 후속 작업: ALB 삭제 완료 후 aws_security_group.lb-4dzo8v_sg 별도 삭제
# ──────────────────────────────────────────────
# resource "aws_lb" "lb-4dzo8v" {
#   name               = "lb-4dzo8v"
#   internal           = false
#   load_balancer_type = "application"
#   security_groups    = [aws_security_group.lb-4dzo8v_sg.id]
#   subnets            = var.public_subnet_ids
#
#   tags = {
#     Name = "lb-4dzo8v"
#   }
# }

# ──────────────────────────────────────────────
# 삭제 대상 ALB — lb-ucc4pu
# 삭제 전 반드시 아래 검증 완료:
#   1. aws elbv2 describe-load-balancers --names lb-ucc4pu \
#        --query 'LoadBalancers[*].DNSName'
#      → Route53 및 외부 DNS에서 참조 여부 확인
#   2. aws elbv2 describe-listeners --load-balancer-arn <ARN>
#      → 결과 비어 있어야 삭제 가능
#   3. terraform plan -out=cleanup.plan && terraform apply cleanup.plan
#
# 제거 이유: 30일간 request_count = 0, active_connection_count = 0
#            $16.43/월 ALB 고정 비용 낭비 (findings.json 기준)
# 후속 작업: ALB 삭제 완료 후 aws_security_group.lb-ucc4pu_sg 별도 삭제
# ──────────────────────────────────────────────
# resource "aws_lb" "lb-ucc4pu" {
#   name               = "lb-ucc4pu"
#   internal           = false
#   load_balancer_type = "application"
#   security_groups    = [aws_security_group.lb-ucc4pu_sg.id]
#   subnets            = var.public_subnet_ids
#
#   tags = {
#     Name = "lb-ucc4pu"
#   }
# }

# ──────────────────────────────────────────────
# 유지 대상 ALB — lb-ffxzco (정상 운영 중)
# 주의: aws_lb_listener 없이 ALB만 존재하면 트래픽 수신 불가.
#       반드시 aws_lb_listener 리소스와 함께 운영할 것.
# ──────────────────────────────────────────────
resource "aws_lb" "lb-ffxzco" {
  name               = "lb-ffxzco"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.lb-ffxzco_sg.id]
  subnets            = var.public_subnet_ids

  # FinOps 개선: 안전 속성 추가
  enable_deletion_protection = true  # 실수 삭제 방지
  idle_timeout               = 60    # 기본값 명시 (초)

  tags = {
    Name        = "lb-ffxzco"
    Environment = var.environment  # 필수 태그 추가
    Owner       = var.owner        # 필수 태그 추가
    CreatedFor  = var.created_for  # 필수 태그 추가
    ManagedBy   = "terraform"
  }
}

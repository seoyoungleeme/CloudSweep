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

# ALB targeted for deletion - lb-4dzo8v
# Complete the checks below before deletion:
#   1. aws elbv2 describe-load-balancers --names lb-4dzo8v \
#        --query 'LoadBalancers[*].DNSName'
#      Check whether Route53 or external DNS references the returned DNS name.
#   2. aws elbv2 describe-listeners --load-balancer-arn <ARN>
#      Deletion is allowed only if the result is empty.
#   3. terraform plan -out=cleanup.plan && terraform apply cleanup.plan
#
# Removal reason: request_count = 0 and active_connection_count = 0 for 30 days.
#                 $16.43/mo ALB fixed cost waste, based on findings.json.
# Follow-up task: after ALB deletion is complete, delete aws_security_group.lb-4dzo8v_sg separately.
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

# ALB targeted for deletion - lb-ucc4pu
# Complete the checks below before deletion:
#   1. aws elbv2 describe-load-balancers --names lb-ucc4pu \
#        --query 'LoadBalancers[*].DNSName'
#      Check whether Route53 or external DNS references the returned DNS name.
#   2. aws elbv2 describe-listeners --load-balancer-arn <ARN>
#      Deletion is allowed only if the result is empty.
#   3. terraform plan -out=cleanup.plan && terraform apply cleanup.plan
#
# Removal reason: request_count = 0 and active_connection_count = 0 for 30 days.
#                 $16.43/mo ALB fixed cost waste, based on findings.json.
# Follow-up task: after ALB deletion is complete, delete aws_security_group.lb-ucc4pu_sg separately.
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

# ALB to retain - lb-ffxzco (operating normally)
# Note: if only the ALB exists without an aws_lb_listener, it cannot receive traffic.
#       Operate it together with an aws_lb_listener resource.
resource "aws_lb" "lb-ffxzco" {
  name               = "lb-ffxzco"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.lb-ffxzco_sg.id]
  subnets            = var.public_subnet_ids

  # FinOps improvement: add safety attributes.
  enable_deletion_protection = true  # Prevent accidental deletion.
  idle_timeout               = 60    # Explicit default value in seconds.

  tags = {
    Name        = "lb-ffxzco"
    Environment = var.environment  # Add required tag.
    Owner       = var.owner        # Add required tag.
    CreatedFor  = var.created_for  # Add required tag.
    ManagedBy   = "terraform"
  }
}
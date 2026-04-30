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

# ══════════════════════════════════════════════════════════════════════════════
# FINOPS: 8 log groups changed from retention_in_days = 0 (never expire)
# to retention_in_days = 90. Expected storage reduction: 4,800 GB → 1,440 GB.
# Estimated savings: ~$100.80/mo (~$1,209.60/yr).
# ══════════════════════════════════════════════════════════════════════════════

resource "aws_cloudwatch_log_group" "cloudwatch-log-group-upz5kj" {
  retention_in_days = 90 # was 0 (infinite) — cost-control fix

  tags = {
    Name = "cloudwatch-log-group-upz5kj"
  }
}

resource "aws_cloudwatch_log_group" "cloudwatch-log-group-ct2yww" {
  retention_in_days = 90 # was 0 (infinite) — cost-control fix

  tags = {
    Name = "cloudwatch-log-group-ct2yww"
  }
}

resource "aws_cloudwatch_log_group" "cloudwatch-log-group-iy9ws4" {
  retention_in_days = 90 # was 0 (infinite) — cost-control fix

  tags = {
    Name = "cloudwatch-log-group-iy9ws4"
  }
}

resource "aws_cloudwatch_log_group" "cloudwatch-log-group-0tnecc" {
  retention_in_days = 90 # was 0 (infinite) — cost-control fix

  tags = {
    Name = "cloudwatch-log-group-0tnecc"
  }
}

resource "aws_cloudwatch_log_group" "cloudwatch-log-group-ur71ym" {
  retention_in_days = 90 # was 0 (infinite) — cost-control fix

  tags = {
    Name = "cloudwatch-log-group-ur71ym"
  }
}

resource "aws_cloudwatch_log_group" "cloudwatch-log-group-nlkcxf" {
  retention_in_days = 90 # was 0 (infinite) — cost-control fix

  tags = {
    Name = "cloudwatch-log-group-nlkcxf"
  }
}

resource "aws_cloudwatch_log_group" "cloudwatch-log-group-d3eyyn" {
  retention_in_days = 90 # was 0 (infinite) — cost-control fix

  tags = {
    Name = "cloudwatch-log-group-d3eyyn"
  }
}

resource "aws_cloudwatch_log_group" "cloudwatch-log-group-havj8r" {
  retention_in_days = 90 # was 0 (infinite) — cost-control fix

  tags = {
    Name = "cloudwatch-log-group-havj8r"
  }
}

# Already compliant — retention_in_days = 90, no changes needed

resource "aws_cloudwatch_log_group" "cloudwatch-log-group-2rjgcu" {
  retention_in_days = 90

  tags = {
    Name = "cloudwatch-log-group-2rjgcu"
  }
}

resource "aws_cloudwatch_log_group" "cloudwatch-log-group-t4vfyn" {
  retention_in_days = 90

  tags = {
    Name = "cloudwatch-log-group-t4vfyn"
  }
}

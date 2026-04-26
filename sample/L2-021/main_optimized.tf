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

# FinOps Q1: receive_wait_time_seconds 0 → 20 (롱 폴링 활성화)
# 5큐 × 2,000,000 빈 수신/day → 큐당 $24/mo, 합계 $120/mo 낭비
# 변경은 큐 재생성 없이 in-place 적용 가능 (no message loss)

resource "aws_sqs_queue" "sqs-queue-83ackx" {
  # FinOps Q1: 빈 수신 2,000,000/day (polling_interval=100ms tight loop)
  # 롱 폴링으로 전환 → 빈 수신 667× 감소, $24/mo 절감
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = 30
  messages_per_day           = 1000
  empty_receives_per_day     = 2000000
  polling_interval_ms        = 100

  tags = {
    Name = "sqs-queue-83ackx"
  }
}

resource "aws_sqs_queue" "sqs-queue-ackuzr" {
  # FinOps Q1: 빈 수신 2,000,000/day (polling_interval=100ms tight loop)
  # 롱 폴링으로 전환 → 빈 수신 667× 감소, $24/mo 절감
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = 30
  messages_per_day           = 1000
  empty_receives_per_day     = 2000000
  polling_interval_ms        = 100

  tags = {
    Name = "sqs-queue-ackuzr"
  }
}

resource "aws_sqs_queue" "sqs-queue-mwbrm2" {
  # FinOps Q1: 빈 수신 2,000,000/day (polling_interval=100ms tight loop)
  # 롱 폴링으로 전환 → 빈 수신 667× 감소, $24/mo 절감
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = 30
  messages_per_day           = 1000
  empty_receives_per_day     = 2000000
  polling_interval_ms        = 100

  tags = {
    Name = "sqs-queue-mwbrm2"
  }
}

resource "aws_sqs_queue" "sqs-queue-hil4hg" {
  # FinOps Q1: 빈 수신 2,000,000/day (polling_interval=100ms tight loop)
  # 롱 폴링으로 전환 → 빈 수신 667× 감소, $24/mo 절감
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = 30
  messages_per_day           = 1000
  empty_receives_per_day     = 2000000
  polling_interval_ms        = 100

  tags = {
    Name = "sqs-queue-hil4hg"
  }
}

resource "aws_sqs_queue" "sqs-queue-mq58yd" {
  # FinOps Q1: 빈 수신 2,000,000/day (polling_interval=100ms tight loop)
  # 롱 폴링으로 전환 → 빈 수신 667× 감소, $24/mo 절감
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = 30
  messages_per_day           = 1000
  empty_receives_per_day     = 2000000
  polling_interval_ms        = 100

  tags = {
    Name = "sqs-queue-mq58yd"
  }
}

# 아래 두 큐는 이미 receive_wait_time_seconds=20 — 변경 없음 (정상 baseline)
resource "aws_sqs_queue" "sqs-queue-ouczyn" {
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = 30
  messages_per_day           = 5000
  empty_receives_per_day     = 3000
  polling_interval_ms        = 20000

  tags = {
    Name = "sqs-queue-ouczyn"
  }
}

resource "aws_sqs_queue" "sqs-queue-gq175x" {
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = 30
  messages_per_day           = 5000
  empty_receives_per_day     = 3000
  polling_interval_ms        = 20000

  tags = {
    Name = "sqs-queue-gq175x"
  }
}

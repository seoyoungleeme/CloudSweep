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

resource "aws_lambda_function" "lambda-function-zspoqd" {
  function_name = "lambda-function-zspoqd"
  role          = aws_iam_role.lambda-function-zspoqd_role.arn
  handler       = "index.handler"
  runtime       = "nodejs18.x"

  memory_size = 1024
  # FinOps M2: 타임아웃 축소 900s → 10s
  # 30일 duration_ms: avg=2,016ms / p99=5,897ms — timeout의 0.66% 수준
  # 에러율 2.1% × 50,000 calls/day → 에러 시 900 GB-초 낭비
  # 10초로 줄이면 에러 비용 99% 절감, 절감액 $180/mo ($2,160/yr)
  # 참고: p99 기준 공식 권장값 18s, pricing_note 기준 10s → 10s 적용
  timeout     = 10

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-zspoqd"
  }
}

resource "aws_lambda_function" "lambda-function-mfra1j" {
  function_name = "lambda-function-mfra1j"
  role          = aws_iam_role.lambda-function-mfra1j_role.arn
  handler       = "index.handler"
  runtime       = "nodejs18.x"

  memory_size = 1024
  # FinOps M2: 타임아웃 축소 900s → 10s
  # 30일 duration_ms: avg=2,014ms / p99=5,350ms — timeout의 0.66% 수준
  # 에러율 1.9% × 50,000 calls/day → 에러 시 900 GB-초 낭비
  # 10초로 줄이면 에러 비용 99% 절감, 절감액 $180/mo ($2,160/yr)
  timeout     = 10

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-mfra1j"
  }
}

# 아래 함수는 timeout=30 — 변경 없음 (healthy baseline)
resource "aws_lambda_function" "lambda-function-6apyi7" {
  function_name = "lambda-function-6apyi7"
  role          = aws_iam_role.lambda-function-6apyi7_role.arn
  handler       = "index.handler"
  runtime       = "nodejs18.x"

  memory_size = 1024
  timeout     = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-6apyi7"
  }
}

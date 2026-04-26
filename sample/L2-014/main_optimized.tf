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

resource "aws_lambda_function" "lambda-function-192d7g" {
  function_name = "lambda-function-192d7g"
  role          = aws_iam_role.lambda-function-192d7g_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  # FinOps M1: 메모리 다운사이즈 3008MB → 512MB
  # 30일 평균 실사용량 99.91MB (max 100MB) — 3008MB의 3.3% 사용
  # pricing_note 기준 절감액: $250/mo ($3,000/yr)
  memory_size = 512
  timeout     = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-192d7g"
  }
}

resource "aws_lambda_function" "lambda-function-ctcl0s" {
  function_name = "lambda-function-ctcl0s"
  role          = aws_iam_role.lambda-function-ctcl0s_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  # FinOps M1: 메모리 다운사이즈 3008MB → 512MB
  # 30일 평균 실사용량 99.99MB (max 100MB) — 3008MB의 3.3% 사용
  # pricing_note 기준 절감액: $250/mo ($3,000/yr)
  memory_size = 512
  timeout     = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-ctcl0s"
  }
}

resource "aws_lambda_function" "lambda-function-jfafoa" {
  function_name = "lambda-function-jfafoa"
  role          = aws_iam_role.lambda-function-jfafoa_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  # FinOps M1: 메모리 다운사이즈 3008MB → 512MB
  # 30일 평균 실사용량 99.89MB (max 100MB) — 3008MB의 3.3% 사용
  # pricing_note 기준 절감액: $250/mo ($3,000/yr)
  memory_size = 512
  timeout     = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-jfafoa"
  }
}

# 아래 두 함수는 이미 512MB — 변경 없음 (baseline)
resource "aws_lambda_function" "lambda-function-7fw8rk" {
  function_name = "lambda-function-7fw8rk"
  role          = aws_iam_role.lambda-function-7fw8rk_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  memory_size = 512
  timeout     = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-7fw8rk"
  }
}

resource "aws_lambda_function" "lambda-function-q49wt1" {
  function_name = "lambda-function-q49wt1"
  role          = aws_iam_role.lambda-function-q49wt1_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  memory_size = 512
  timeout     = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-q49wt1"
  }
}

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
# FINOPS: lambda-function-192d7g, -ctcl0s, -jfafoa — memory reduced from
# 3008 MB to 512 MB. Max observed memory used: ~100 MB (3.3% of 3008 MB)
# over 30 days. Duration flat at ~100ms — workload is not CPU-bound.
# Estimated savings: ~$250/mo per function (~$750/mo total, ~$9,000/yr).
#
# PREREQUISITE: Monitor Duration, Errors, and Throttles for 7 days post-deploy.
# Roll back to the previous function version if duration increases > 20%
# or any errors appear. See finops_report.md for the CloudWatch commands.
# ══════════════════════════════════════════════════════════════════════════════

resource "aws_lambda_function" "lambda-function-192d7g" {
  function_name = "lambda-function-192d7g"
  role          = aws_iam_role.lambda-function-192d7g_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  memory_size = 512  # was 3008 — right-sized to max_used(100 MB) × 1.5 headroom; 512 MB per cost_report guidance

  timeout = 30

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

  memory_size = 512  # was 3008 — right-sized; same pattern as 192d7g

  timeout = 30

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

  memory_size = 512  # was 3008 — right-sized; same pattern as 192d7g

  timeout = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-jfafoa"
  }
}

# ── No primary changes — within acceptable utilization range ──────────────────
# Secondary: run Lambda Power Tuning before reducing below 512 MB.
# At 19.5% memory utilization (100 MB used of 512 MB), reducing to 256 MB
# may save an additional ~$24/mo per function, but duration impact must be
# confirmed experimentally first.

resource "aws_lambda_function" "lambda-function-7fw8rk" {
  function_name = "lambda-function-7fw8rk"
  role          = aws_iam_role.lambda-function-7fw8rk_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  memory_size = 512

  timeout = 30

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

  timeout = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-q49wt1"
  }
}

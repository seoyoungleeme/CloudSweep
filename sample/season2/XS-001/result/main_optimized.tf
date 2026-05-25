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

locals {
  xs001_dashboard_name      = "xs001-request-amplification"
  xs001_s3_metric_filter_id = "request-amplification"
}

# ---------------------------------------------------------------------------
# Component 1/2 - Lambda resources are preserved.
#
# The three 3008 MB functions are memory-rightsize candidates, but this
# revision does not change memory because the provided metrics omit
# Invocations, Errors, Throttles, and dependency-call attribution.
# Validate with Lambda Power Tuning after request-amplification telemetry is
# available.
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "comp1_lambda-function-abothk" {
  function_name = "lambda-function-abothk"
  role          = aws_iam_role.lambda-function-abothk_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  memory_size = 3008
  timeout     = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-abothk"
  }
}

resource "aws_lambda_function" "comp1_lambda-function-exijoh" {
  function_name = "lambda-function-exijoh"
  role          = aws_iam_role.lambda-function-exijoh_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  memory_size = 3008
  timeout     = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-exijoh"
  }
}

resource "aws_lambda_function" "comp1_lambda-function-qh890g" {
  function_name = "lambda-function-qh890g"
  role          = aws_iam_role.lambda-function-qh890g_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  memory_size = 3008
  timeout     = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-qh890g"
  }
}

resource "aws_lambda_function" "comp1_lambda-function-9xajdu" {
  function_name = "lambda-function-9xajdu"
  role          = aws_iam_role.lambda-function-9xajdu_role.arn
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
    Name = "lambda-function-9xajdu"
  }
}

resource "aws_lambda_function" "comp1_lambda-function-ulqkdr" {
  function_name = "lambda-function-ulqkdr"
  role          = aws_iam_role.lambda-function-ulqkdr_role.arn
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
    Name = "lambda-function-ulqkdr"
  }
}

# ---------------------------------------------------------------------------
# Component 2/2 - S3 buckets are preserved.
#
# No lifecycle rule is added yet. The supplied metrics show request activity
# but do not include object age, storage class mix, BucketSizeBytes, or
# per-prefix access frequency. First attribute request cost to callers.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "comp2_s3-bucket-d5xzop" {
  bucket = "data-lake-raw"

  tags = {
    Name = "data-lake-raw"
  }
}

resource "aws_s3_bucket" "comp2_s3-bucket-adax9b" {
  bucket = "data-lake-archive"

  tags = {
    Name = "data-lake-archive"
  }
}

resource "aws_s3_bucket" "comp2_s3-bucket-j6o036" {
  bucket = "data-lake-curated"

  tags = {
    Name = "data-lake-curated"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "comp2_s3-bucket-j6o036" {
  bucket = aws_s3_bucket.comp2_s3-bucket-j6o036.id

  rule {
    id     = "transition-rule"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "GLACIER"
    }
  }
}

# ---------------------------------------------------------------------------
# XS-001 evidence-first optimization: enable request attribution.
#
# These S3 metrics configurations make request metrics available in
# CloudWatch. The dashboard below compares S3 GetRequests to Lambda
# Invocations, which is the required evidence for confirming or rejecting the
# cache-miss/request-amplification hypothesis.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket_metric" "comp2_s3-bucket-d5xzop_request_amplification" {
  bucket = aws_s3_bucket.comp2_s3-bucket-d5xzop.id
  name   = local.xs001_s3_metric_filter_id
}

resource "aws_s3_bucket_metric" "comp2_s3-bucket-adax9b_request_amplification" {
  bucket = aws_s3_bucket.comp2_s3-bucket-adax9b.id
  name   = local.xs001_s3_metric_filter_id
}

resource "aws_s3_bucket_metric" "comp2_s3-bucket-j6o036_request_amplification" {
  bucket = aws_s3_bucket.comp2_s3-bucket-j6o036.id
  name   = local.xs001_s3_metric_filter_id
}

resource "aws_cloudwatch_dashboard" "xs001_request_amplification" {
  dashboard_name = local.xs001_dashboard_name

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6

        properties = {
          region = "us-east-1"
          title  = "XS-001 S3 GETs per Lambda invocation"
          view   = "timeSeries"
          period = 3600
          stat   = "Sum"

          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", "lambda-function-abothk", { id = "inv_abothk", visible = false }],
            [".", ".", ".", "lambda-function-exijoh", { id = "inv_exijoh", visible = false }],
            [".", ".", ".", "lambda-function-qh890g", { id = "inv_qh890g", visible = false }],
            ["AWS/S3", "GetRequests", "BucketName", "data-lake-raw", "FilterId", local.xs001_s3_metric_filter_id, { id = "get_raw", visible = false }],
            [".", ".", ".", "data-lake-archive", ".", local.xs001_s3_metric_filter_id, { id = "get_archive", visible = false }],
            [{
              expression = "IF((inv_abothk + inv_exijoh + inv_qh890g) > 0, (get_raw + get_archive) / (inv_abothk + inv_exijoh + inv_qh890g), 0)"
              id         = "get_per_invocation"
              label      = "S3 GETs per Lambda invocation"
            }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6

        properties = {
          region = "us-east-1"
          title  = "XS-001 Lambda duration and S3 GET trend"
          view   = "timeSeries"
          period = 3600

          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", "lambda-function-abothk", { stat = "p99", id = "dur_abothk" }],
            [".", ".", ".", "lambda-function-exijoh", { stat = "p99", id = "dur_exijoh" }],
            [".", ".", ".", "lambda-function-qh890g", { stat = "p99", id = "dur_qh890g" }],
            ["AWS/S3", "GetRequests", "BucketName", "data-lake-raw", "FilterId", local.xs001_s3_metric_filter_id, { stat = "Sum", id = "get_raw_trend", yAxis = "right" }],
            [".", ".", ".", "data-lake-archive", ".", local.xs001_s3_metric_filter_id, { stat = "Sum", id = "get_archive_trend", yAxis = "right" }]
          ]
        }
      }
    ]
  })

  depends_on = [
    aws_s3_bucket_metric.comp2_s3-bucket-d5xzop_request_amplification,
    aws_s3_bucket_metric.comp2_s3-bucket-adax9b_request_amplification,
    aws_s3_bucket_metric.comp2_s3-bucket-j6o036_request_amplification
  ]
}

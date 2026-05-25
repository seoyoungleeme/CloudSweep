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


# ═══════════════════════════════════════════════════════════════
# Component 1/3 · finops-lambda · L2-014
# Savings: ~$750/mo | memory 3008 → 256 MB (3 functions)
# Price source: cost_report.json pricing_note
#   "3008MB → 512MB로 줄이면 함수당 약 $250/mo 절감 (3 함수 합계 $750/mo)"
#   256 MB chosen: p99 observed = 100 MB, low variance (min: 82–91 MB)
#   2.56× headroom over p99 across 720 datapoints.
#   ⚠ PREREQUISITE: validate with AWS Lambda Power Tuning in staging
#   before production rollout — duration metrics not available in
#   provided data. Monitor Duration p99, Errors, Throttles post-deploy.
# ═══════════════════════════════════════════════════════════════

# [CHANGED] memory_size: 3008 → 256 MB
# Evidence: p99 MaxMemoryUsed = 100 MB, min = 91.21 MB (720 datapoints)
# Savings: ~$250/mo | Rollback: revert memory_size to 3008
resource "aws_lambda_function" "comp1_lambda-function-atrjum" {
  function_name = "lambda-function-atrjum"
  role          = aws_iam_role.lambda-function-atrjum_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  memory_size = 256 # was 3008; p99 100 MB, low variance (min 91.21 MB), 2.5x headroom
  timeout     = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-atrjum"
  }
}

# [CHANGED] memory_size: 3008 → 256 MB
# Evidence: p99 MaxMemoryUsed = 100 MB, min = 82.39 MB (720 datapoints)
# Savings: ~$250/mo | Rollback: revert memory_size to 3008
resource "aws_lambda_function" "comp1_lambda-function-37781v" {
  function_name = "lambda-function-37781v"
  role          = aws_iam_role.lambda-function-37781v_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  memory_size = 256 # was 3008; p99 100 MB, low variance (min 82.39 MB), 2.5x headroom
  timeout     = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-37781v"
  }
}

# [CHANGED] memory_size: 3008 → 256 MB
# Evidence: p99 MaxMemoryUsed = 100 MB, min = 86.75 MB (720 datapoints)
# Savings: ~$250/mo | Rollback: revert memory_size to 3008
resource "aws_lambda_function" "comp1_lambda-function-luzj7m" {
  function_name = "lambda-function-luzj7m"
  role          = aws_iam_role.lambda-function-luzj7m_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  memory_size = 256 # was 3008; p99 100 MB, low variance (min 86.75 MB), 2.5x headroom
  timeout     = 30

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }

  tags = {
    Name = "lambda-function-luzj7m"
  }
}

# [UNCHANGED] memory_size = 512 MB — utilization ~19.5%; no waste flagged
resource "aws_lambda_function" "comp1_lambda-function-5z9us6" {
  function_name = "lambda-function-5z9us6"
  role          = aws_iam_role.lambda-function-5z9us6_role.arn
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
    Name = "lambda-function-5z9us6"
  }
}

# [UNCHANGED] memory_size = 512 MB — utilization ~19.5%; no waste flagged
resource "aws_lambda_function" "comp1_lambda-function-ancpd0" {
  function_name = "lambda-function-ancpd0"
  role          = aws_iam_role.lambda-function-ancpd0_role.arn
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
    Name = "lambda-function-ancpd0"
  }
}


# ═══════════════════════════════════════════════════════════════
# Component 2/3 · finops-s3 · L1-011
# Savings: ~$152/mo | lifecycle added to raw + archive buckets
# Price source: cost_report.json pricing_note
#   (8,192 GB eligible × $0.019/GB Standard→GLACIER differential)
# ═══════════════════════════════════════════════════════════════

# [CHANGED] + lifecycle (STANDARD_IA at 30d, GLACIER at 90d, MPU abort 7d)
# Savings: part of aggregate ~$152/mo cost_report savings
resource "aws_s3_bucket" "comp2_s3-bucket-554gvl" {
  bucket = "data-lake-raw"

  tags = {
    Name = "data-lake-raw"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "comp2_s3-bucket-554gvl" {
  bucket = aws_s3_bucket.comp2_s3-bucket-554gvl.id

  rule {
    id     = "raw-tiering"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# [CHANGED] + lifecycle (STANDARD_IA at 30d, GLACIER at 90d, MPU abort 7d)
# NOTE: Active reads observed on this bucket. If access is truly rare,
#       reduce STANDARD_IA window — validate with owner before changing.
# Savings: part of aggregate ~$152/mo cost_report savings
resource "aws_s3_bucket" "comp2_s3-bucket-xu5s05" {
  bucket = "data-lake-archive"

  tags = {
    Name = "data-lake-archive"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "comp2_s3-bucket-xu5s05" {
  bucket = aws_s3_bucket.comp2_s3-bucket-xu5s05.id

  rule {
    id     = "archive-tiering"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# [UNCHANGED] is_problem: false — existing lifecycle (90d Glacier transition) preserved as-is
resource "aws_s3_bucket" "comp2_s3-bucket-9m71do" {
  bucket = "data-lake-curated"

  tags = {
    Name = "data-lake-curated"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "comp2_s3-bucket-9m71do" {
  bucket = aws_s3_bucket.comp2_s3-bucket-9m71do.id

  rule {
    id     = "transition-rule"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "GLACIER"
    }
  }
}


# ═══════════════════════════════════════════════════════════════
# Component 3/3 · finops-dynamodb · L1-010
# Savings: ~$522/mo (cost_report conservative)
# Price source: cost_report.json pricing_note
# Rules triggered: D1 (HIGH), D2 (HIGH), D3 (MEDIUM)
# Change: wouiv4 right-sized 5000→120 RCU, 1000→120 WCU
#         + Application Auto Scaling added (min 100, max 500, 70% target)
# No change: 8q8f66 (PAY_PER_REQUEST, is_problem: false)
# ═══════════════════════════════════════════════════════════════

# [CHANGED] read_capacity 5000→120, write_capacity 1000→120
# Evidence: RCU avg 100.0 (2.0% util), WCU avg 87.94 (8.8% util), p99=100, zero throttling
resource "aws_dynamodb_table" "comp3_dynamodb-table-wouiv4" {
  name         = "dynamodb-table-wouiv4"
  billing_mode = "PROVISIONED"

  hash_key = "id"

  attribute {
    name = "id"
    type = "S"
  }

  read_capacity  = 120 # was 5000; avg 100 RCU (2.0% util), p99=100; 20% headroom
  write_capacity = 120 # was 1000; avg 87.94 WCU (8.8% util), p99=100; 20% headroom

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "dynamodb-table-wouiv4"
  }
}

# [ADDED] Auto Scaling — read capacity
resource "aws_appautoscaling_target" "comp3_dynamodb_wouiv4_read" {
  service_namespace  = "dynamodb"
  resource_id        = "table/dynamodb-table-wouiv4"
  scalable_dimension = "dynamodb:table:ReadCapacityUnits"
  min_capacity       = 100
  max_capacity       = 500
}

resource "aws_appautoscaling_policy" "comp3_dynamodb_wouiv4_read" {
  name               = "dynamodb-wouiv4-read-scaling"
  service_namespace  = "dynamodb"
  resource_id        = aws_appautoscaling_target.comp3_dynamodb_wouiv4_read.resource_id
  scalable_dimension = aws_appautoscaling_target.comp3_dynamodb_wouiv4_read.scalable_dimension
  policy_type        = "TargetTrackingScaling"

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "DynamoDBReadCapacityUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# [ADDED] Auto Scaling — write capacity
resource "aws_appautoscaling_target" "comp3_dynamodb_wouiv4_write" {
  service_namespace  = "dynamodb"
  resource_id        = "table/dynamodb-table-wouiv4"
  scalable_dimension = "dynamodb:table:WriteCapacityUnits"
  min_capacity       = 100
  max_capacity       = 500
}

resource "aws_appautoscaling_policy" "comp3_dynamodb_wouiv4_write" {
  name               = "dynamodb-wouiv4-write-scaling"
  service_namespace  = "dynamodb"
  resource_id        = aws_appautoscaling_target.comp3_dynamodb_wouiv4_write.resource_id
  scalable_dimension = aws_appautoscaling_target.comp3_dynamodb_wouiv4_write.scalable_dimension
  policy_type        = "TargetTrackingScaling"

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "DynamoDBWriteCapacityUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# [UNCHANGED] PAY_PER_REQUEST — no waste detected
resource "aws_dynamodb_table" "comp3_dynamodb-table-8q8f66" {
  name         = "dynamodb-table-8q8f66"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "id"

  attribute {
    name = "id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "dynamodb-table-8q8f66"
  }
}

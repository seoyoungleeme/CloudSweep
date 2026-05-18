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
# Component 1/3 · seeded from L2-014
# ═══════════════════════════════════════════════════════════════

resource "aws_lambda_function" "comp1_lambda-function-atrjum" {
  function_name = "lambda-function-atrjum"
  role          = aws_iam_role.lambda-function-atrjum_role.arn
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
    Name = "lambda-function-atrjum"
  }
}

resource "aws_lambda_function" "comp1_lambda-function-37781v" {
  function_name = "lambda-function-37781v"
  role          = aws_iam_role.lambda-function-37781v_role.arn
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
    Name = "lambda-function-37781v"
  }
}

resource "aws_lambda_function" "comp1_lambda-function-luzj7m" {
  function_name = "lambda-function-luzj7m"
  role          = aws_iam_role.lambda-function-luzj7m_role.arn
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
    Name = "lambda-function-luzj7m"
  }
}

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
# Component 2/3 · seeded from L1-011
# ═══════════════════════════════════════════════════════════════

resource "aws_s3_bucket" "comp2_s3-bucket-554gvl" {
  bucket = "data-lake-raw"

  tags = {
    Name        = "data-lake-raw"
  }
}

resource "aws_s3_bucket" "comp2_s3-bucket-xu5s05" {
  bucket = "data-lake-archive"

  tags = {
    Name        = "data-lake-archive"
  }
}

resource "aws_s3_bucket" "comp2_s3-bucket-9m71do" {
  bucket = "data-lake-curated"

  tags = {
    Name        = "data-lake-curated"
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
# Component 3/3 · seeded from L1-010
# ═══════════════════════════════════════════════════════════════

resource "aws_dynamodb_table" "comp3_dynamodb-table-wouiv4" {
  name         = "dynamodb-table-wouiv4"
  billing_mode = "PROVISIONED"

  hash_key  = "id"

  attribute {
    name = "id"
    type = "S"
  }

  read_capacity  = 5000
  write_capacity = 1000

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "dynamodb-table-wouiv4"
  }
}

resource "aws_dynamodb_table" "comp3_dynamodb-table-8q8f66" {
  name         = "dynamodb-table-8q8f66"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "id"

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

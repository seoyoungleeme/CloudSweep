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
# Component 1/2 · seeded from L2-014
# ═══════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════
# Component 2/2 · seeded from L1-011
# ═══════════════════════════════════════════════════════════════

resource "aws_s3_bucket" "comp2_s3-bucket-d5xzop" {
  bucket = "data-lake-raw"

  tags = {
    Name        = "data-lake-raw"
  }
}

resource "aws_s3_bucket" "comp2_s3-bucket-adax9b" {
  bucket = "data-lake-archive"

  tags = {
    Name        = "data-lake-archive"
  }
}

resource "aws_s3_bucket" "comp2_s3-bucket-j6o036" {
  bucket = "data-lake-curated"

  tags = {
    Name        = "data-lake-curated"
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

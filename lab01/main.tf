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

# Generated as read-only evidence from MiniStack. Do not apply this file blindly.
resource "aws_s3_bucket" "deprecated_frontend_assets_2eccac5f" {
  bucket = "deprecated-frontend-assets"
}

resource "aws_s3_bucket" "dev_scratch_jan2024_baedda61" {
  bucket = "dev-scratch-jan2024"
  tags = {
    Environment = "development"
    Team = "dev-team"
  }
}

resource "aws_s3_bucket" "old_migration_dump_v2_92e45c70" {
  bucket = "old-migration-dump-v2"
}

resource "aws_s3_bucket" "poc_analytics_raw_c8fe879d" {
  bucket = "poc-analytics-raw"
  tags = {
    Environment = "development"
    Team = "data"
  }
}

resource "aws_s3_bucket" "prod_application_logs_b175eb14" {
  bucket = "prod-application-logs"
  tags = {
    CostCenter = "CC-001"
    Environment = "production"
    Project = "main-platform"
    Team = "platform"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "prod_application_logs_b175eb14_lifecycle" {
  bucket = aws_s3_bucket.prod_application_logs_b175eb14.id

  rule {
    id     = "auto-tiering"
    status = "Enabled"
    filter {}
    # Additional rule details remain in parsed_input.json.
  }
}

resource "aws_s3_bucket" "prod_backups_73171b8b" {
  bucket = "prod-backups"
  tags = {
    CostCenter = "CC-001"
    Environment = "production"
    Project = "main-platform"
    Team = "infra"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "prod_backups_73171b8b_lifecycle" {
  bucket = aws_s3_bucket.prod_backups_73171b8b.id

  rule {
    id     = "auto-tiering"
    status = "Enabled"
    filter {}
    # Additional rule details remain in parsed_input.json.
  }
}

resource "aws_s3_bucket" "prod_user_uploads_12685b76" {
  bucket = "prod-user-uploads"
  tags = {
    CostCenter = "CC-001"
    Environment = "production"
    Project = "main-platform"
    Team = "product"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "prod_user_uploads_12685b76_lifecycle" {
  bucket = aws_s3_bucket.prod_user_uploads_12685b76.id

  rule {
    id     = "auto-tiering"
    status = "Enabled"
    filter {}
    # Additional rule details remain in parsed_input.json.
  }
}

resource "aws_s3_bucket" "staging_logs_backup_713531e3" {
  bucket = "staging-logs-backup"
  tags = {
    Environment = "staging"
    Team = "infra"
  }
}

resource "aws_s3_bucket" "temp_data_export_2024q1_8c684d70" {
  bucket = "temp-data-export-2024q1"
  tags = {
    Environment = "development"
  }
}

resource "aws_s3_bucket" "test_results_archive_0218008b" {
  bucket = "test-results-archive"
  tags = {
    Environment = "test"
  }
}

resource "aws_s3_bucket" "unused_ml_training_data_d8cafa08" {
  bucket = "unused-ml-training-data"
}

resource "aws_lambda_function" "prod_api_handler_7e07f704" {
  function_name = "prod-api-handler"
  role          = "arn:aws:iam::000000000000:role/lambda-execution-role"
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size = 256
  timeout     = 10
  tags = {
    CostCenter = "CC-001"
    Environment = "production"
    Project = "main-platform"
    Team = "platform"
  }
}

resource "aws_lambda_function" "prod_event_processor_abb841c3" {
  function_name = "prod-event-processor"
  role          = "arn:aws:iam::000000000000:role/lambda-execution-role"
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size = 512
  timeout     = 30
  tags = {
    CostCenter = "CC-001"
    Environment = "production"
    Project = "main-platform"
    Team = "platform"
  }
}

resource "aws_lambda_function" "waste_csv_parser_b9b557af" {
  function_name = "waste-csv-parser"
  role          = "arn:aws:iam::000000000000:role/lambda-execution-role"
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size = 3008
  timeout     = 300
  tags = {
    Environment = "production"
    Team = "backend"
  }
}

resource "aws_lambda_function" "waste_email_sender_89f0878f" {
  function_name = "waste-email-sender"
  role          = "arn:aws:iam::000000000000:role/lambda-execution-role"
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size = 2048
  timeout     = 120
  tags = {
    Environment = "production"
    Team = "backend"
  }
}

resource "aws_lambda_function" "waste_health_checker_ed3ddab0" {
  function_name = "waste-health-checker"
  role          = "arn:aws:iam::000000000000:role/lambda-execution-role"
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size = 2048
  timeout     = 300
  tags = {
    Environment = "production"
    Team = "backend"
  }
}

resource "aws_lambda_function" "waste_log_forwarder_6027503c" {
  function_name = "waste-log-forwarder"
  role          = "arn:aws:iam::000000000000:role/lambda-execution-role"
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size = 1024
  timeout     = 60
  tags = {
    Environment = "production"
    Team = "backend"
  }
}

resource "aws_lambda_function" "waste_notification_push_67b6b765" {
  function_name = "waste-notification-push"
  role          = "arn:aws:iam::000000000000:role/lambda-execution-role"
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size = 1536
  timeout     = 60
  tags = {
    Environment = "production"
    Team = "backend"
  }
}

resource "aws_lambda_function" "waste_thumbnail_gen_c7700c49" {
  function_name = "waste-thumbnail-gen"
  role          = "arn:aws:iam::000000000000:role/lambda-execution-role"
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size = 3008
  timeout     = 300
  tags = {
    Environment = "production"
    Team = "backend"
  }
}

resource "aws_db_instance" "prod_api_db_0e77730c" {
  identifier              = "prod-api-db"
  engine                  = "postgres"
  engine_version          = "15.3"
  instance_class          = "db.t3.medium"
  storage_type            = "gp2"
  allocated_storage       = 20
  multi_az                = true
  backup_retention_period = 7
  tags = {
    CostCenter = "CC-001"
    Environment = "production"
    Project = "main-platform"
    Team = "platform"
  }
}

resource "aws_db_instance" "dev_analytics_db_64c7c4dc" {
  identifier              = "dev-analytics-db"
  engine                  = "postgres"
  engine_version          = "15.3"
  instance_class          = "db.r5.xlarge"
  storage_type            = "gp2"
  allocated_storage       = 20
  multi_az                = true
  backup_retention_period = 30
  tags = {
    Environment = "development"
    Team = "analytics"
  }
}

resource "aws_db_instance" "dev_reporting_db_2b0272f3" {
  identifier              = "dev-reporting-db"
  engine                  = "mysql"
  engine_version          = "8.0.33"
  instance_class          = "db.m5.large"
  storage_type            = "gp2"
  allocated_storage       = 20
  multi_az                = true
  backup_retention_period = 21
  tags = {
    Environment = "development"
    Team = "analytics"
  }
}

resource "aws_db_instance" "staging_cache_db_19cba437" {
  identifier              = "staging-cache-db"
  engine                  = "postgres"
  engine_version          = "15.3"
  instance_class          = "db.r5.large"
  storage_type            = "gp2"
  allocated_storage       = 20
  multi_az                = true
  backup_retention_period = 14
  tags = {
    Environment = "staging"
    Team = "analytics"
  }
}

resource "aws_cloudwatch_log_group" "app_access_logs_c7cd043c" {
  name = "/app/access-logs"
}

resource "aws_cloudwatch_log_group" "app_debug_logs_a665405d" {
  name = "/app/debug-logs"
}

resource "aws_cloudwatch_log_group" "aws_ecs_staging_service_9c27ece4" {
  name = "/aws/ecs/staging-service"
}

resource "aws_cloudwatch_log_group" "aws_lambda_waste_email_sender_ad90ae5d" {
  name = "/aws/lambda/waste-email-sender"
}

resource "aws_cloudwatch_log_group" "aws_lambda_waste_thumbnail_gen_e1080972" {
  name = "/aws/lambda/waste-thumbnail-gen"
}

resource "aws_cloudwatch_log_group" "aws_rds_dev_analytics_db_55513166" {
  name = "/aws/rds/dev-analytics-db"
}

# Domain Aliases for Cost Slice Matching

Match `service` field (case-insensitive) in `cost_report.json` against:

| Domain | Aliases |
|--------|---------|
| ec2 | EC2, Amazon EC2, Amazon Elastic Compute Cloud |
| bedrock | Bedrock, Amazon Bedrock |
| sagemaker | SageMaker, Amazon SageMaker, Amazon SageMaker AI |
| lambda | Lambda, AWS Lambda |
| s3 | S3, Amazon S3, Amazon Simple Storage Service |
| dynamodb | DynamoDB, Amazon DynamoDB |
| rds | RDS, Amazon RDS, Amazon Relational Database Service |
| ebs | EBS, Amazon EBS, Amazon Elastic Block Store |
| ecs | ECS, Amazon ECS, AWS Fargate, Fargate |
| elasticache | ElastiCache, Amazon ElastiCache |
| sqs | SQS, Amazon SQS, Amazon Simple Queue Service |
| kinesis | Kinesis, Amazon Kinesis, Kinesis Data Streams |
| nat | NAT Gateway, NAT, Amazon VPC |
| tgw | Transit Gateway, AWS Transit Gateway |
| organizations | Organizations, AWS Organizations |
| cloudwatch | CloudWatch, Amazon CloudWatch |
| cloudwatch-alarm | CloudWatch, Amazon CloudWatch |
| cloudfront | CloudFront, Amazon CloudFront |
| stepfunctions | Step Functions, AWS Step Functions, SFN |
| vpc-endpoint | VPC Endpoint, PrivateLink, Amazon VPC |
| elb | ELB, ALB, Elastic Load Balancing |

Fallback: check top-level `services[].type` if present.

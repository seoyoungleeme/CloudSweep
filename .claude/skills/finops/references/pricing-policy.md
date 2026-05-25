# Pricing & MCP Policy

## MCP availability

Never block analysis because an MCP tool is unavailable. Fall back to scenario
data or static rule prices.

## Pricing priority

1. `cost_report.json` explicit waste or `pricing_note`.
2. `aws-pricing` MCP — `mcp__aws-pricing__get_pricing`.
3. Domain skill `rules/*.json` static price.
4. `[estimate]` — state the assumed price explicitly.

## MCP service codes

| Domain | service_code |
|--------|-------------|
| lambda | `AWSLambda` |
| dynamodb | `AmazonDynamoDB` |
| s3 | `AmazonS3` |
| elb | `AWSELB` |
| rds | `AmazonRDS` |
| elasticache | `AmazonElastiCache` |
| kinesis | `AmazonKinesis` |
| sqs | `AmazonSQS` |
| nat / ebs / ec2 | `AmazonEC2` |
| cloudwatch / cloudwatch-alarm | `AmazonCloudWatch` |
| cloudfront | `AmazonCloudFront` |
| stepfunctions | `AWSStepFunctions` |

## Call template

- `region`: Terraform provider region (default `us-east-1`).
- `output_options`: `{"pricing_terms": ["OnDemand"]}`.
- Tight `filters`; `max_results=10`.
- Cross-check only — keep scenario `pricing_note` as final estimate.

## Docs

For every remediation, call `mcp__aws-docs__search_documentation` and cite the
URL in the report.

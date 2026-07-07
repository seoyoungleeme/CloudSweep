# Pricing & MCP Policy

## MCP Availability

Never block analysis because an MCP tool is unavailable. Fall back to scenario
data or static rule prices.

## Pricing Priority

1. `cost_report.json` explicit waste or `pricing_note`.
2. `aws-pricing` MCP via `mcp__aws-pricing__get_pricing`, delivered via the
   **shared, cross-scenario cache** at `pricing_cache/{domain}_pricing_model.json`
   (repo root, NOT under any scenario's `result/`) in response to
   `result/.machine/{domain}_pricing_request.json` (currently: s3, lambda, rds, elb,
   ecs, elasticache; see `schemas/pricing-model.schema.json`). Tagged
   `pricing_source: aws_public_pricing_model`, confidence capped at MEDIUM.
   **The cache is shared because a region+SKU's public list price is the same
   regardless of which scenario asked for it** -- when writing, read the
   existing cache file if it exists and merge new `sku_key` entries into its
   `unit_prices` list; never overwrite or drop previously-resolved entries.
3. Domain skill `rules/*.json` static price. Tagged
   `pricing_source: static_fallback_estimate`, pricing confidence LOW.
4. `reasonable_estimate` is a LOW-confidence approval-review lane when the
   quantity and unit prices are available but safety, ownership, or dependency
   guardrails are incomplete. Keep it separate from evidence-backed savings.
5. `unmeasured` means no quantity or price evidence is available; state `$0.00`
   explicitly rather than guessing a resource size or price.

Priority 2 is optional, asynchronous enrichment: a missing or not-yet-supplied
`pricing_model.json` never blocks a finding from being priced at tier 3 or 4.
It only means a later run (for this scenario, or any other scenario in the
same region) can upgrade the number once a public price is supplied.

### `sku_key` Convention

- **s3**: `f"{region}|{storage_class}"`, e.g. `us-east-1|STANDARD`.
- **lambda**: `f"{region}|{architecture}"`, e.g. `us-east-1|x86_64`.
- **rds**: `f"{region}|{engine}|{instance_class}|{deployment}"`, e.g.
  `us-east-1|postgres|db.r5.xlarge|multi_az`.
- **elb**: `f"{region}|{load_balancer_type}|{charge_type}"`, e.g.
  `us-east-1|application|load_balancer_hour`.
- **ecs**: `f"{region}|fargate|linux|{architecture}|{charge_type}"`, e.g.
  `us-east-1|fargate|linux|x86_64|vcpu_hour`.
- **elasticache**: `f"{region}|{engine}|{node_type}|node_hour"`, e.g.
  `us-east-1|redis|cache.r6g.large|node_hour`.

## MCP Service Codes

| Domain | service_code |
|--------|--------------|
| lambda | `AWSLambda` |
| bedrock | `AmazonBedrock` |
| sagemaker | `AmazonSageMaker` |
| dynamodb | `AmazonDynamoDB` |
| s3 | `AmazonS3` |
| elb | `AWSELB` |
| ecs | `AmazonECS` |
| rds | `AmazonRDS` |
| elasticache | `AmazonElastiCache` |
| kinesis | `AmazonKinesis` |
| sqs | `AmazonSQS` |
| nat / ebs / ec2 | `AmazonEC2` |
| cloudwatch / cloudwatch-alarm | `AmazonCloudWatch` |
| cloudfront | `AmazonCloudFront` |
| stepfunctions | `AWSStepFunctions` |

## Call Template

- `region`: Terraform provider region (default `us-east-1`).
- `output_options`: `{"pricing_terms": ["OnDemand"]}`.
- Tight `filters`; `max_results=10`.
- Cross-check only; keep scenario `pricing_note` as final estimate.

## Docs

For every remediation, call `mcp__aws-docs__search_documentation` and cite the
URL in the report.

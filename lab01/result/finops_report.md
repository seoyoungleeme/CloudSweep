# CloudSweep LangGraph Report

**Scenario**: lab01
**Run date**: 2026-06-22
**Intent**: waste_optimization
**Execution plan**: domain_analysis -> report

## Evidence Inventory

| Evidence | Status |
|----------|--------|
| terraform | present |
| genai_evidence | missing |
| metrics | present |
| cost_report | missing |
| parsed_input | present |
| existing_findings | missing |
| cost_explorer | missing |
| anomalies | missing |
| cloudtrail | missing |

## Domain Nodes

Domains detected: s3, lambda, rds, cloudwatch

| Domain | Resource | Rule | Source | Status | Severity | Confidence | Monthly Savings |
|--------|----------|------|--------|--------|----------|------------|-----------------|
| s3 | poc_analytics_raw_c8fe879d | S3_LIFECYCLE_POLICY:V1 | langgraph | machine_analyzed | MEDIUM | MEDIUM | $0.00 |
| s3 | test_results_archive_0218008b | S3_LIFECYCLE_POLICY:V1 | langgraph | machine_analyzed | MEDIUM | MEDIUM | $0.00 |
| lambda | waste_csv_parser_b9b557af | LAMBDA_RIGHTSIZE_POLICY:L1 | langgraph | machine_analyzed | HIGH | MEDIUM | $0.00 |
| lambda | waste_thumbnail_gen_c7700c49 | LAMBDA_RIGHTSIZE_POLICY:L1 | langgraph | machine_analyzed | HIGH | MEDIUM | $0.00 |
| rds | prod_api_db_0e77730c | RDS_R2_LOW_UTILIZATION | langgraph+claude_skill | skill_needs_evidence | HIGH | LOW | $0.00 |
| rds | prod_api_db_0e77730c | RDS_R5_GP2_STORAGE | langgraph+claude_skill | skill_needs_evidence | MEDIUM | LOW | $0.00 |
| rds | dev_analytics_db_64c7c4dc | RDS_R1_NONPROD_MULTI_AZ | langgraph+claude_skill | skill_needs_evidence | MEDIUM | LOW | $0.00 |
| rds | dev_analytics_db_64c7c4dc | RDS_R2_LOW_UTILIZATION | langgraph+claude_skill | skill_needs_evidence | HIGH | LOW | $0.00 |
| rds | dev_analytics_db_64c7c4dc | RDS_R5_GP2_STORAGE | langgraph+claude_skill | skill_needs_evidence | MEDIUM | LOW | $0.00 |
| rds | dev_reporting_db_2b0272f3 | RDS_R1_NONPROD_MULTI_AZ | langgraph+claude_skill | skill_needs_evidence | MEDIUM | LOW | $0.00 |
| rds | dev_reporting_db_2b0272f3 | RDS_R2_LOW_UTILIZATION | langgraph+claude_skill | skill_needs_evidence | HIGH | LOW | $0.00 |
| rds | dev_reporting_db_2b0272f3 | RDS_R5_GP2_STORAGE | langgraph+claude_skill | skill_needs_evidence | MEDIUM | LOW | $0.00 |
| rds | staging_cache_db_19cba437 | RDS_R1_NONPROD_MULTI_AZ | langgraph+claude_skill | skill_needs_evidence | MEDIUM | LOW | $0.00 |
| rds | staging_cache_db_19cba437 | RDS_R2_LOW_UTILIZATION | langgraph+claude_skill | skill_needs_evidence | HIGH | LOW | $0.00 |
| rds | staging_cache_db_19cba437 | RDS_R5_GP2_STORAGE | langgraph+claude_skill | skill_needs_evidence | MEDIUM | LOW | $0.00 |
| cloudwatch | app_access_logs_c7cd043c | CLOUDWATCH_RETENTION_POLICY:C1 | langgraph | machine_analyzed | HIGH | HIGH | $0.00 |
| cloudwatch | app_debug_logs_a665405d | CLOUDWATCH_RETENTION_POLICY:C1 | langgraph | machine_analyzed | HIGH | HIGH | $0.00 |
| cloudwatch | aws_ecs_staging_service_9c27ece4 | CLOUDWATCH_RETENTION_POLICY:C1 | langgraph | machine_analyzed | HIGH | HIGH | $0.00 |
| cloudwatch | aws_lambda_waste_email_sender_ad90ae5d | CLOUDWATCH_RETENTION_POLICY:C1 | langgraph | machine_analyzed | HIGH | HIGH | $0.00 |
| cloudwatch | aws_lambda_waste_thumbnail_gen_e1080972 | CLOUDWATCH_RETENTION_POLICY:C1 | langgraph | machine_analyzed | HIGH | HIGH | $0.00 |
| cloudwatch | aws_rds_dev_analytics_db_55513166 | CLOUDWATCH_RETENTION_POLICY:C1 | langgraph | machine_analyzed | HIGH | HIGH | $0.00 |

Conservative estimated monthly savings: **$0.00**

## Enrichment

- pricing: provider=local-fallback, findings=21, failures=0
- documentation: provider=local-fallback, findings=21, failures=0

## Approval

Status: **not_required**

## Cross-Domain Review

- Lambda and S3 are both present; check request amplification before treating storage lifecycle as the only driver.

## Graph Trace

- inventory: metrics, parsed_input, terraform
- plan: domain_analysis -> report
- domains: s3, lambda, rds, cloudwatch
- domain fan-out: 4 branch(es)
- domain result: s3 (2 finding(s))
- domain result: lambda (2 finding(s))
- domain result: rds (11 finding(s))
- domain result: cloudwatch (6 finding(s))
- domain findings: 21
- pricing enrichment: local-fallback, failures=0
- documentation enrichment: local-fallback, failures=0
- approval gate: not required
- cross-domain notes: 1

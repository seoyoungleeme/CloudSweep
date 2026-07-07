# CloudSweep LangGraph Report

**Scenario**: lab01
**Run date**: 2026-07-07
**Intent**: waste_optimization
**Execution plan**: domain_analysis -> report

## Token & Cost Usage

| Metric | Value |
|--------|-------|
| Model | claude-sonnet-5 |
| Input tokens | 50 |
| Output tokens | 27,284 |
| Cache write tokens | 102,344 |
| Cache read tokens | 3,626,734 |
| Total tokens | 3,756,412 |
| Estimated cost (USD) | $1.8812 |

_Recovered from this machine's Claude Code session transcript for the current CloudSweep completion window. This is a single total for complex Skill work, AI review, and report polish performed in that window (standard Sonnet 5 list pricing, $3/$15 per MTok); deterministic Python graph rendering itself does not call an LLM and subagent-session token spend is excluded._

## Executive Summary

lab01 has $696.05/mo in evidence-backed savings and a further $569.40/mo of reasonable-estimate upside pending safety review, across 30 findings in s3, lambda, rds, and cloudwatch. The confirmed savings come from five Lambda memory rightsizing candidates and three RDS Multi-AZ removals on non-production instances, all priced from AWS public on-demand rates. No cost_report.json was available for this scenario, so pricing relies on the public-pricing waterfall and static fallback estimates rather than billed line items.

- Lambda: 5 functions over-allocated relative to observed p99 memory usage; rightsizing saves $23.72/mo, priced from AWS Lambda's public GB-second rate.
- RDS: 3 non-production instances (dev_analytics_db, dev_reporting_db, staging_cache_db) run Multi-AZ without a stated SLA/DR requirement; removing it saves $672.33/mo, priced from AWS public RDS instance-hour rates.
- RDS instance downsizing on those same 3 instances is a separate $569.40/mo reasonable-estimate path -- treat it as an alternative to the Multi-AZ removal above, not an additional stack of savings on the same instance.
- S3: 8 buckets lack a lifecycle policy but bucket size was not observed, so savings remain unmeasured rather than assumed.
- CloudWatch: 6 log groups have no retention policy, but all report zero stored bytes -- confirm this is a metrics gap rather than genuinely empty groups before counting these as cost recovery.

Key caveats:
- No cost_report.json was available; all pricing is modeled from AWS public rates or the domain's static fallback price, not billed cost data.
- RDS R1 (drop Multi-AZ) and R2 (downsize instance) findings on the same 3 instances are alternatives from the same cost baseline -- do not sum them as independent savings.
- S3 and most RDS storage/utilization findings are unmeasured because bucket size and IOPS/storage metrics were not collected for this scenario; this is a data-collection gap, not evidence of no waste.
- One Lambda finding (waste-notification-push) carries a mislabeled evidence trigger value (waste_name_lte_35_pct); the priced savings figure is unaffected, but the label should be fixed at the source.

## AI Review

30 findings reviewed across s3 (8), lambda (5), rds (11), and cloudwatch (6). Lambda rightsizing and RDS Multi-AZ findings are well-evidenced and correctly priced via the public pricing waterfall. Two structural issues found: RDS R1/R2 alternatives on the same three instances are not mutually exclusive in the totals, and all six CloudWatch retention findings report stored_bytes=0, which may mean there is no cost to actually recover yet.

Review notes:
- RDS_R1_NONPROD_MULTI_AZ and RDS_R2_LOW_UTILIZATION are computed independently on the same three instances (dev_analytics_db_64c7c4dc, dev_reporting_db_2b0272f3, staging_cache_db_19cba437). R1 assumes the instance stays at its current class and only Multi-AZ is removed; R2 assumes Multi-AZ stays on and only the instance class shrinks. These are alternative remediation paths from the same baseline, not additive -- report R1 as evidence-backed savings and keep R2 as separate reasonable-estimate upside unless a reviewer explicitly chooses the downsizing path instead.
- prod_api_db_0e77730c correctly has no R1 finding (production, Multi-AZ retained) -- consistent with the R1 rule only firing on non-production instances.
- Lambda cross-domain refs (waste_email_sender, waste_thumbnail_gen) to their CloudWatch log groups are backed by observed dependency_facts with fact_ids -- safe to treat as observed, not hypothesis.
- The three cloudwatch_retention_review hypotheses (app_access_logs, app_debug_logs, aws_ecs_staging_service) correctly stay as unconfirmed hypotheses with no fact_ids -- no compute/RDS association was observed for them, so they should not be escalated to observed cross-domain statements.
- RDS Reserved Instance coverage (rule R3) was correctly not raised as a finding for prod_api_db_0e77730c: cost_report.json is absent, so there is no billing evidence to confirm an on-demand-only baseline. Raising R3 here would be speculation, not a finding.

Quality flags:
- All 6 CloudWatch log-group retention findings (CLOUDWATCH_RETENTION_POLICY:C1) report stored_bytes=0. A log group with zero stored bytes has no storage cost to recover today, so setting a retention policy on it is a preventive/governance action, not a monthly-savings action -- confirm this is a metrics collection gap (e.g. logs written after the collection window) rather than genuinely empty groups before representing these as cost-saving candidates in the same table as priced findings.
- All 8 S3 lifecycle findings and the RDS R2/R5 findings on prod_api_db_0e77730c are unmeasured for the same root cause (bucket_size / IOPS-storage evidence not collected) -- this is a data-collection gap on the MiniStack/metrics side, not a detection weakness; worth noting as a follow-up evidence request rather than closing these out as no-waste.
- Lambda finding cs-d45e08bd096c (waste-notification-push) carries evidence value trigger=waste_name_lte_35_pct. This reads like a mislabeled trigger constant (compare to the other four Lambda findings' trigger=p99_memory_lte_25_pct) rather than a real metric name. It does not affect the priced savings figure, but the label should be corrected in the rule engine so evidence stays legible.

## Priority Summary

- Evidence-backed monthly savings: **$696.05**
- Reasonable estimate upside: **$569.40**
- Unmeasured candidates: **19**

| Status | Domain | Resource | Rule | Monthly Savings |
|--------|--------|----------|------|-----------------|
| priced | rds | dev-analytics-db | RDS_R1_NONPROD_MULTI_AZ | $365.00 |
| reasonable_estimate | rds | dev-analytics-db | RDS_R2_LOW_UTILIZATION | $365.00 |
| priced | rds | staging-cache-db | RDS_R1_NONPROD_MULTI_AZ | $182.50 |
| reasonable_estimate | rds | staging-cache-db | RDS_R2_LOW_UTILIZATION | $153.30 |
| priced | rds | dev-reporting-db | RDS_R1_NONPROD_MULTI_AZ | $124.83 |
| reasonable_estimate | rds | dev-reporting-db | RDS_R2_LOW_UTILIZATION | $51.10 |
| priced | lambda | waste-csv-parser | LAMBDA_RIGHTSIZE_POLICY:L1 | $7.21 |
| priced | lambda | waste-thumbnail-gen | LAMBDA_RIGHTSIZE_POLICY:L1 | $7.21 |

_Reasonable estimates are review upside, not additive guaranteed savings._

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

| Domain | Resource | Display Name | Rule | Source | Status | Severity | Confidence | Pricing Confidence | Savings Status | Pricing Source | Monthly Savings |
|--------|----------|--------------|------|--------|--------|----------|------------|--------------------|----------------|----------------|-----------------|
| s3 | deprecated_frontend_assets_2eccac5f | deprecated-frontend-assets | S3_LIFECYCLE_POLICY:V1 | langgraph | machine_analyzed | MEDIUM | MEDIUM | LOW | unmeasured | unmeasured | $0.00 |
| s3 | dev_scratch_jan2024_baedda61 | dev-scratch-jan2024 | S3_LIFECYCLE_POLICY:V1 | langgraph | machine_analyzed | MEDIUM | MEDIUM | LOW | unmeasured | unmeasured | $0.00 |
| s3 | old_migration_dump_v2_92e45c70 | old-migration-dump-v2 | S3_LIFECYCLE_POLICY:V1 | langgraph | machine_analyzed | MEDIUM | MEDIUM | LOW | unmeasured | unmeasured | $0.00 |
| s3 | poc_analytics_raw_c8fe879d | poc-analytics-raw | S3_LIFECYCLE_POLICY:V1 | langgraph | machine_analyzed | MEDIUM | MEDIUM | LOW | unmeasured | unmeasured | $0.00 |
| s3 | staging_logs_backup_713531e3 | staging-logs-backup | S3_LIFECYCLE_POLICY:V1 | langgraph | machine_analyzed | MEDIUM | MEDIUM | LOW | unmeasured | unmeasured | $0.00 |
| s3 | temp_data_export_2024q1_8c684d70 | temp-data-export-2024q1 | S3_LIFECYCLE_POLICY:V1 | langgraph | machine_analyzed | MEDIUM | MEDIUM | LOW | unmeasured | unmeasured | $0.00 |
| s3 | test_results_archive_0218008b | test-results-archive | S3_LIFECYCLE_POLICY:V1 | langgraph | machine_analyzed | MEDIUM | MEDIUM | LOW | unmeasured | unmeasured | $0.00 |
| s3 | unused_ml_training_data_d8cafa08 | unused-ml-training-data | S3_LIFECYCLE_POLICY:V1 | langgraph | machine_analyzed | MEDIUM | MEDIUM | LOW | unmeasured | unmeasured | $0.00 |
| lambda | waste_csv_parser_b9b557af | waste-csv-parser | LAMBDA_RIGHTSIZE_POLICY:L1 | langgraph | machine_analyzed | HIGH | MEDIUM | MEDIUM | priced | aws_public_pricing_model | $7.21 |
| lambda | waste_email_sender_89f0878f | waste-email-sender | LAMBDA_RIGHTSIZE_POLICY:L1 | langgraph | machine_analyzed | HIGH | MEDIUM | MEDIUM | priced | aws_public_pricing_model | $3.72 |
| lambda | waste_health_checker_ed3ddab0 | waste-health-checker | LAMBDA_RIGHTSIZE_POLICY:L1 | langgraph | machine_analyzed | HIGH | MEDIUM | MEDIUM | priced | aws_public_pricing_model | $3.72 |
| lambda | waste_notification_push_67b6b765 | waste-notification-push | LAMBDA_RIGHTSIZE_POLICY:L1 | langgraph | machine_analyzed | HIGH | LOW | MEDIUM | priced | aws_public_pricing_model | $1.86 |
| lambda | waste_thumbnail_gen_c7700c49 | waste-thumbnail-gen | LAMBDA_RIGHTSIZE_POLICY:L1 | langgraph | machine_analyzed | HIGH | MEDIUM | MEDIUM | priced | aws_public_pricing_model | $7.21 |
| rds | prod_api_db_0e77730c | prod-api-db | RDS_R2_LOW_UTILIZATION | claude_skill | skill_analyzed | HIGH | LOW | LOW | unmeasured | unmeasured | $0.00 |
| rds | prod_api_db_0e77730c | prod-api-db | RDS_R5_GP2_STORAGE | claude_skill | skill_analyzed | MEDIUM | LOW | LOW | unmeasured | unmeasured | $0.00 |
| rds | dev_analytics_db_64c7c4dc | dev-analytics-db | RDS_R1_NONPROD_MULTI_AZ | claude_skill | skill_analyzed | MEDIUM | LOW | MEDIUM | priced | aws_public_pricing_model | $365.00 |
| rds | dev_analytics_db_64c7c4dc | dev-analytics-db | RDS_R2_LOW_UTILIZATION | claude_skill | skill_analyzed | HIGH | LOW | LOW | reasonable_estimate | reasonable_estimate | $365.00 |
| rds | dev_analytics_db_64c7c4dc | dev-analytics-db | RDS_R5_GP2_STORAGE | claude_skill | skill_analyzed | MEDIUM | LOW | LOW | unmeasured | unmeasured | $0.00 |
| rds | dev_reporting_db_2b0272f3 | dev-reporting-db | RDS_R1_NONPROD_MULTI_AZ | claude_skill | skill_analyzed | MEDIUM | LOW | MEDIUM | priced | aws_public_pricing_model | $124.83 |
| rds | dev_reporting_db_2b0272f3 | dev-reporting-db | RDS_R2_LOW_UTILIZATION | claude_skill | skill_analyzed | HIGH | LOW | LOW | reasonable_estimate | reasonable_estimate | $51.10 |
| rds | dev_reporting_db_2b0272f3 | dev-reporting-db | RDS_R5_GP2_STORAGE | claude_skill | skill_analyzed | MEDIUM | LOW | LOW | unmeasured | unmeasured | $0.00 |
| rds | staging_cache_db_19cba437 | staging-cache-db | RDS_R1_NONPROD_MULTI_AZ | claude_skill | skill_analyzed | MEDIUM | LOW | MEDIUM | priced | aws_public_pricing_model | $182.50 |
| rds | staging_cache_db_19cba437 | staging-cache-db | RDS_R2_LOW_UTILIZATION | claude_skill | skill_analyzed | HIGH | LOW | LOW | reasonable_estimate | reasonable_estimate | $153.30 |
| rds | staging_cache_db_19cba437 | staging-cache-db | RDS_R5_GP2_STORAGE | claude_skill | skill_analyzed | MEDIUM | LOW | LOW | unmeasured | unmeasured | $0.00 |
| cloudwatch | app_access_logs_c7cd043c | /app/access-logs | CLOUDWATCH_RETENTION_POLICY:C1 | langgraph | machine_analyzed | HIGH | HIGH | LOW | unmeasured | unmeasured | $0.00 |
| cloudwatch | app_debug_logs_a665405d | /app/debug-logs | CLOUDWATCH_RETENTION_POLICY:C1 | langgraph | machine_analyzed | HIGH | HIGH | LOW | unmeasured | unmeasured | $0.00 |
| cloudwatch | aws_ecs_staging_service_9c27ece4 | /aws/ecs/staging-service | CLOUDWATCH_RETENTION_POLICY:C1 | langgraph | machine_analyzed | HIGH | HIGH | LOW | unmeasured | unmeasured | $0.00 |
| cloudwatch | aws_lambda_waste_email_sender_ad90ae5d | /aws/lambda/waste-email-sender | CLOUDWATCH_RETENTION_POLICY:C1 | langgraph | machine_analyzed | HIGH | HIGH | LOW | unmeasured | unmeasured | $0.00 |
| cloudwatch | aws_lambda_waste_thumbnail_gen_e1080972 | /aws/lambda/waste-thumbnail-gen | CLOUDWATCH_RETENTION_POLICY:C1 | langgraph | machine_analyzed | HIGH | HIGH | LOW | unmeasured | unmeasured | $0.00 |
| cloudwatch | aws_rds_dev_analytics_db_55513166 | /aws/rds/dev-analytics-db | CLOUDWATCH_RETENTION_POLICY:C1 | langgraph | machine_analyzed | HIGH | HIGH | LOW | unmeasured | unmeasured | $0.00 |

Estimated monthly savings: **$696.05**
Reasonable estimate upside: **$569.40**

## Savings Notes

- s3/deprecated-frontend-assets: unmeasured; bucket_size_not_observed
- s3/dev-scratch-jan2024: unmeasured; bucket_size_not_observed
- s3/old-migration-dump-v2: unmeasured; bucket_size_not_observed
- s3/poc-analytics-raw: unmeasured; bucket_size_not_observed
- s3/staging-logs-backup: unmeasured; bucket_size_not_observed
- s3/temp-data-export-2024q1: unmeasured; bucket_size_not_observed
- s3/test-results-archive: unmeasured; bucket_size_not_observed
- s3/unused-ml-training-data: unmeasured; bucket_size_not_observed
- lambda/waste-csv-parser: priced; priced_from_lambda_gb_seconds
- lambda/waste-email-sender: priced; priced_from_lambda_gb_seconds
- lambda/waste-health-checker: priced; priced_from_lambda_gb_seconds
- lambda/waste-notification-push: priced; priced_from_lambda_gb_seconds
- lambda/waste-thumbnail-gen: priced; priced_from_lambda_gb_seconds
- rds/prod-api-db: unmeasured; safety_or_target_pricing_evidence_missing
- rds/prod-api-db: unmeasured; storage_price_or_iops_evidence_missing
- rds/dev-analytics-db: priced; priced_from_public_rds_instance_hours
- rds/dev-analytics-db: reasonable_estimate; safety_or_target_pricing_evidence_missing
- rds/dev-analytics-db: unmeasured; storage_price_or_iops_evidence_missing
- rds/dev-reporting-db: priced; priced_from_public_rds_instance_hours
- rds/dev-reporting-db: reasonable_estimate; safety_or_target_pricing_evidence_missing
- rds/dev-reporting-db: unmeasured; storage_price_or_iops_evidence_missing
- rds/staging-cache-db: priced; priced_from_public_rds_instance_hours
- rds/staging-cache-db: reasonable_estimate; safety_or_target_pricing_evidence_missing
- rds/staging-cache-db: unmeasured; storage_price_or_iops_evidence_missing
- cloudwatch//app/access-logs: unmeasured; stored_bytes_zero_or_missing
- cloudwatch//app/debug-logs: unmeasured; stored_bytes_zero_or_missing
- cloudwatch//aws/ecs/staging-service: unmeasured; stored_bytes_zero_or_missing
- cloudwatch//aws/lambda/waste-email-sender: unmeasured; stored_bytes_zero_or_missing
- cloudwatch//aws/lambda/waste-thumbnail-gen: unmeasured; stored_bytes_zero_or_missing
- cloudwatch//aws/rds/dev-analytics-db: unmeasured; stored_bytes_zero_or_missing

## Enrichment

- pricing: provider=local-fallback, findings=30, failures=0
- documentation: provider=local-fallback, findings=30, failures=0

## Approval

Status: **not_required**

## Cross-Domain Review

- CloudWatch log group aws_lambda_waste_email_sender_ad90ae5d is associated with Lambda waste_email_sender_89f0878f; review retention and emitted log volume together.
- CloudWatch log group aws_lambda_waste_thumbnail_gen_e1080972 is associated with Lambda waste_thumbnail_gen_c7700c49; review retention and emitted log volume together.
- CloudWatch log group aws_rds_dev_analytics_db_55513166 is associated with RDS dev_analytics_db_64c7c4dc; review retention and emitted log volume together.

## Cross-Domain Hypotheses

- [hypothesis] CloudWatch log group /app/access-logs has a retention finding but no observed compute/RDS association in the evidence; review emitted volume and owner before treating it as a cross-domain cost driver.
- [hypothesis] CloudWatch log group /app/debug-logs has a retention finding but no observed compute/RDS association in the evidence; review emitted volume and owner before treating it as a cross-domain cost driver.
- [hypothesis] CloudWatch log group /aws/ecs/staging-service has a retention finding but no observed compute/RDS association in the evidence; review emitted volume and owner before treating it as a cross-domain cost driver.

## Warnings

- Lambda metric inconsistency for prod_api_handler_7e07f704 (prod-api-handler): p99_memory_used_mb=416.7091 exceeds allocated_memory_mb=256; excluded from rightsizing.

## Graph Trace

- inventory: metrics, parsed_input, terraform
- plan: domain_analysis -> report
- domains: s3, lambda, rds, cloudwatch
- domain fan-out: 4 branch(es)
- domain result: s3 (8 finding(s))
- domain result: lambda (5 finding(s))
- domain result: rds (11 finding(s))
- domain result: cloudwatch (6 finding(s))
- domain findings: 30
- pricing requests: none
- pricing enrichment: local-fallback, failures=0
- documentation enrichment: local-fallback, failures=0
- approval gate: not required
- cross-domain notes: 3
- cross-domain hypotheses: 3
- cross-domain annotations: 8 finding(s)
- ai review: loaded
- report polish: loaded

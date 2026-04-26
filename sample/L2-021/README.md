# FinOps Simulation Scenario

## Company Information

| Item | Details |
|------|---------|
| Company Name | MedCloud |
| Industry | Healthcare |
| Employee Count | 6864 |
| Growth Stage | Enterprise |
| Cloud Maturity | high |
| Dedicated FinOps Team | Yes |
| Monthly Cloud Cost | $11,381.59 |

## Background

A stage where multi-account operations, complex networking, and RI/SP management are key challenges.

Cloud costs have recently been increasing faster than expected, so a cost optimization review across the infrastructure has been requested.

## Task

Analyze the provided materials to identify cost waste, then propose specific improvements and estimated savings.

### Provided Materials

1. **Terraform Configuration** (main.tf) - Current infrastructure configuration
2. **Metrics Data** (metrics/metrics.json) - 30 days of CloudWatch metrics
3. **Cost Report** (cost_report.json) - 6-month cost history

### Expected Deliverables

1. Identified cost issues and supporting evidence
2. Root cause analysis
3. Specific remediation plan
4. Estimated monthly savings

| Difficulty | Related Services | Category |
|------------|------------------|----------|
| L2 | SQS | API Call Waste |
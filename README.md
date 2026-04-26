# CloudSweep

CloudSweep is a Claude Code-native FinOps toolkit for detecting and eliminating AWS cloud waste.

## Repository Layout

```text
.claude/
  skills/
    finops/          # Orchestrator skill that routes to sub-skills by resource type
    finops-elb/      # Detects unused ALB/ELB resources
    finops-ebs/      # Detects orphaned EBS snapshots
    finops-rds/      # Detects overprovisioned RDS instances
    finops-s3/       # Detects S3 noncurrent version accumulation
sample/
  L1-004/            # Sample scenario: RDS overprovisioning (CargoNet)
  L1-005/            # Sample scenario: unused ALB detection
  L1-007/            # Sample scenario: unused EC2 plus orphaned EBS (CargoNet)
  L1-012/            # Sample scenario: S3 noncurrent version waste (CargoNet)
```

## Trigger Keywords

`FinOps`, `cloud cost`, `cost analysis`, `AWS waste`

## Usage

Open a sample scenario and ask Claude Code to run a FinOps analysis. The orchestrator skill selects the matching service-specific skill, reads the Terraform, metrics, and cost report files, then produces an optimized Terraform file and FinOps report when enough evidence is available.
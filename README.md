# CloudSweep

CloudSweep is a Claude Code–native FinOps toolkit for detecting and eliminating AWS cloud waste.
Skills are loaded automatically when Claude Code is opened in this directory.

---

## Project Structure

```
CloudSweep/
├── .claude/
│   └── skills/
│       ├── finops/          # Orchestrator skill — routes to sub-skills by resource type
│       ├── finops-elb/      # Sub-skill — detects unused ALB/ELB resources
│       │   ├── scripts/     # parser.py · analyzer.py · formatter.py
│       │   └── rules/       # unused_elb.json
│       ├── finops-ebs/      # Sub-skill — detects orphaned EBS snapshots
│       │   ├── scripts/     # parser.py · analyzer.py · formatter.py
│       │   └── rules/       # orphaned_snapshot.json
│       ├── finops-rds/      # Sub-skill — detects overprovisioned RDS instances
│       │   ├── scripts/     # parser.py · analyzer.py · formatter.py
│       │   └── rules/       # overprovisioned_rds.json
│       └── finops-s3/       # Sub-skill — detects S3 noncurrent version accumulation
│           ├── scripts/     # parser.py · analyzer.py · formatter.py
│           └── rules/       # missing_lifecycle_policy.json
└── sample/
    ├── L1-004/              # Sample scenario: RDS overprovisioning (CargoNet)
    ├── L1-005/              # Sample scenario: unused ALB detection
    ├── L1-007/              # Sample scenario: unused EC2 + orphaned EBS (CargoNet)
    └── L1-012/              # Sample scenario: S3 noncurrent version waste (CargoNet)
```

---

## Skills

### `/finops` — FinOps Orchestrator

Inspects input files, detects AWS resource types, and delegates to the appropriate sub-skill.

**Trigger keywords:** `FinOps`, `cloud cost`, `cost analysis`, `AWS waste`, `비용 분석`

### `finops-elb` — ELB/ALB Waste Detector

Analyzes Terraform configs and CloudWatch metrics to identify unused load balancers.
Produces a detailed report with root cause analysis, Terraform fix, and estimated savings.

**Trigger keywords:** `ELB cost`, `ALB waste`, `load balancer optimization`, `unused ELB`

### `finops-ebs` — EBS Snapshot Waste Detector

Identifies orphaned EBS snapshots whose source volumes have been deleted.
Calculates storage cost waste and provides bulk cleanup commands with a hardened Terraform output.

**Trigger keywords:** `EBS snapshot cost`, `orphaned snapshot`, `snapshot cleanup`, `FinOps EBS`

### `finops-rds` — RDS Overprovisioning Detector

Detects two categories of RDS waste: Multi-AZ enabled on non-production environments, and chronically under-utilized instance classes.
Recommends downsizing and Multi-AZ disablement with revised Terraform.

**Trigger keywords:** `RDS cost`, `RDS overprovisioning`, `Multi-AZ dev`, `database optimization`, `FinOps RDS`

### `finops-s3` — S3 Lifecycle Policy Auditor

Detects S3 buckets with versioning enabled but no lifecycle policy, leading to unbounded noncurrent version accumulation.
Generates optimized Terraform with environment-appropriate lifecycle rules.

**Trigger keywords:** `S3 cost`, `S3 versioning`, `noncurrent version`, `lifecycle policy`, `FinOps S3`

---

## Input Files

Each scenario requires up to three files:

| File | Description |
|------|-------------|
| `main.tf` | Terraform resource definitions |
| `metrics.json` | CloudWatch metrics (30-day window) |
| `cost_report.json` | Monthly cost/waste totals |

---

## Sample Scenarios

| Scenario | Service | Category | Description |
|----------|---------|----------|-------------|
| `L1-004` | RDS | Overprovisioning | Multi-AZ on dev + under-utilized instance class |
| `L1-005` | ALB/ELB | Unused | Unused load balancer with zero traffic |
| `L1-007` | EC2, EBS | Unused | Stopped EC2 instances with orphaned EBS snapshots |
| `L1-012` | S3 | Unused | Versioning-enabled buckets without a lifecycle policy |

---

## How to Use

1. Open this repository in Claude Code.
2. Place your input files in a working directory (e.g. `sample/my-scenario/`).
3. Invoke the skill:

```
/finops
```

Claude will locate the input files, run the pipeline, and write `finops_report.md` to your working directory.

---

## Roadmap

- [x] `finops-elb` — unused ALB/ELB detection
- [x] `finops-ebs` — orphaned EBS snapshot detection
- [x] `finops-rds` — RDS overprovisioning detection
- [x] `finops-s3` — S3 storage waste analysis
- [ ] `finops-ec2` — idle EC2 instance detection
- [ ] MCP integration for live AWS data ingestion

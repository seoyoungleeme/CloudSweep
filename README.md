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
│       └── finops-elb/      # Sub-skill — detects unused ALB/ELB resources
│           ├── scripts/     # parser.py · analyzer.py · formatter.py
│           └── rules/       # unused_elb.json
└── sample/
    └── L1-005/              # Sample scenario: unused ALB detection
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

---

## Input Files

Each scenario requires up to three files:

| File | Description |
|------|-------------|
| `main.tf` | Terraform resource definitions |
| `metrics.json` | CloudWatch metrics (30-day window) |
| `cost_report.json` | Monthly cost/waste totals |

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

- [ ] `finops-ec2` — idle EC2 instance detection
- [ ] `finops-rds` — unused RDS instance detection
- [ ] `finops-s3` — S3 storage waste analysis
- [ ] MCP integration for live AWS data ingestion

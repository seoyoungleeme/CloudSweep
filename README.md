# CloudSweep

CloudSweep is a Claude Code-native FinOps toolkit for detecting and eliminating AWS cloud waste.

## Repository Layout

```text
.claude/
  skills/
    finops/                  # Orchestrator — routes to domain skills; evidence-driven routing
    finops-anomaly/          # Cost Explorer spike detection and CloudTrail correlation
    finops-bedrock/          # Bedrock token, throughput, and prompt/semantic cache waste
    finops-cloudwatch/       # CloudWatch log group retention waste
    finops-cloudwatch-alarm/ # High-resolution metric alarm overprovisioning
    finops-dynamodb/         # DynamoDB provisioned capacity waste
    finops-ebs/              # Orphaned EBS snapshots
    finops-ec2/              # EC2 GPU/Inferentia/Trainium scheduling waste
    finops-ecs/              # ECS/Fargate task sizing and autoscaling waste
    finops-elasticache/      # ElastiCache overprovisioning
    finops-elb/              # Idle or unused ALB/ELB
    finops-kinesis/          # Kinesis stream shard overprovisioning
    finops-lambda/           # Lambda memory over-allocation
    finops-nat/              # NAT Gateway replaceable by VPC Gateway Endpoint
    finops-organizations/    # RI/SP pooling and org-level governance
    finops-rds/              # RDS overprovisioning
    finops-s3/               # S3 lifecycle, versioning, and multipart upload waste
    finops-sagemaker/        # SageMaker endpoint autoscaling and instance sizing waste
    finops-sqs/              # SQS queue overprovisioning
    finops-tgw/              # Transit Gateway attachment waste
cloudsweep/                  # LangGraph runtime (Python package)
  __init__.py
  __main__.py                # Entry point for python -m cloudsweep
  graph.py                   # StateGraph definition, nodes, and CLI
sample/
  season1/                   # Season 1 scenarios (L1-*, L2-*, L3-*)
    L1-004/                  # RDS overprovisioning (CargoNet)
    L1-005/                  # Unused ALB detection
    L1-007/                  # Unused EC2 + orphaned EBS (CargoNet)
    L1-012/                  # S3 noncurrent version waste (CargoNet)
    …
  season2/                   # Season 2 scenarios (evidence-driven, multi-domain)
    LV-001/                  # Cost Explorer spike + anomaly incident
    MA-001/                  # Multi-domain: Lambda + S3 + DynamoDB waste
    GENAI-001/               # Terraform-free Bedrock + SageMaker + EC2 evidence
    XS-001/                  # Single-domain subset: Lambda + S3
schemas/
  genai-evidence.schema.json # Canonical GenAI cost and utilization evidence contract
tests/
  test_graph_smoke.py        # Smoke tests: routing, findings, GenAI domain detection
requirements.txt             # langgraph>=1.0,<2.0
```

## Trigger Keywords

`FinOps`, `cloud cost`, `cost analysis`, `AWS waste`, `Bedrock cost`, `SageMaker endpoint cost`, `GPU waste`, `LLM TCO`

## Claude Code Usage

Open a sample scenario and ask Claude Code to run a FinOps analysis. The orchestrator skill inspects available evidence, detects service domains from Terraform, then routes to the matching domain skill or dispatches parallel subagents for multi-domain scenarios.

```
/finops   # or just describe the scenario — the orchestrator picks up FinOps keywords
```

## LangGraph Runtime

CloudSweep also includes an executable LangGraph workflow for repeatable local runs without Claude Code.

```powershell
pip install -r requirements.txt
python -m cloudsweep sample\season2\MA-001 --dry-run   # preview: no files written
python -m cloudsweep sample\season2\MA-001             # write results to result/
python -m unittest discover -s tests                   # run smoke tests
```

The graph runs: `inventory → plan → [anomaly_analysis →] detect_domains → Send(analyze_domain) → collect → pricing/docs enrichment → approval gate → cross-domain review → render`.

The default CLI uses local enrichment fallback and does not pause for approval. Applications can inject `CallableMCPEnrichmentProvider` and use `CloudSweepRuntime` with a checkpointer for interrupt/resume review flows. See `ARCHITECTURE.md`.

### GenAI Evidence Contract

Use `genai_evidence.json` for Terraform-free Bedrock, SageMaker, and EC2 accelerator evidence. The canonical JSON Schema is `schemas/genai-evidence.schema.json`; a complete fixture is available at `sample/season2/GENAI-001/genai_evidence.json`.

Each resource requires `service`, `resource_type`, `configuration`, and `metrics`. Metrics use the existing CloudSweep shape:

```json
{
  "metric_name": {
    "unit": "Count",
    "datapoints": [1, 2, 3]
  }
}
```

The graph merges domain signals from Terraform, `genai_evidence.json`, `metrics.json`, `parsed_input.json`, and `cost_report.json`. This permits cost and usage analysis without a `main.tf` file.

Built-in GenAI analyzers currently cover:

- Bedrock On-Demand/commitment break-even, underutilized commitments, prompt caching, and semantic caching.
- SageMaker endpoint target tracking, scheduled scaling, GPU utilization, and always-on architecture review.
- EC2 GPU/Inferentia/Trainium scheduling, GPU ASG scaling, and residual cost checks.

Default output files are written under the scenario's `result/` directory without replacing challenge artifacts:

- `cloudsweep_graph_report.md`
- `cloudsweep_main_optimized.tf`
- `cloudsweep_graph_state.json`

Use `--standard-output` to write `finops_report.md` and `main_optimized.tf` instead (matching the Claude skill output names).

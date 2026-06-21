# SageMaker FinOps Report Template

Use the orchestrator `references/report-template.md` for unified reports.
For SageMaker findings, include:

| Field | Required Content |
|-------|------------------|
| Endpoint / variant | Endpoint name and variant name |
| Instance shape | Instance type, current count, target count |
| Scaling state | Target tracking, scheduled scaling, or missing |
| Utilization | invocations per instance, GPU/CPU/memory, p95 latency, errors |
| Recommendation | autoscale, schedule, rightsize, or architecture review |
| Savings | instance-hours avoided and pricing source |
| Safety | SLA, model load, min capacity, rollback plan |

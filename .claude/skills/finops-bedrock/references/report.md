# Bedrock FinOps Report Template

Use the orchestrator `references/report-template.md` for unified reports.
For Bedrock-specific findings, include these fields:

## Bedrock Finding Detail

| Field | Required Content |
|-------|------------------|
| Model / route | Model ID, inference profile, agent, or caller route |
| Pricing mode | On-Demand, Provisioned Throughput, reserved tier, or unknown |
| Token evidence | input tokens, output tokens, request count, steady TPM |
| Cache evidence | cache read/write tokens, repeated-prefix tokens, duplicate query rate |
| Recommendation | commitment change, prompt cache, semantic cache, or TCO review |
| Safety checks | freshness, PII, tenant isolation, latency, fallback behavior |
| Savings | monthly formula and pricing source |

Never report a cache hit rate, PT utilization, or break-even threshold that is
not derivable from provided metrics or scenario pricing.

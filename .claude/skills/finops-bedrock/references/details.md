# finops-bedrock - Detailed Rules

## Parse Inputs

From Terraform, identify:
- `aws_bedrock*` and `aws_bedrockagent*` resources.
- Inference profiles, provisioned throughput, invocation logging, agents,
  knowledge bases, and cache-adjacent resources such as ElastiCache, DynamoDB,
  OpenSearch, API Gateway, Lambda, or ECS callers.

From metrics or usage exports, extract:
- request count, input tokens, output tokens, total tokens
- p50/p95/p99 latency and error/throttle rate
- cache read tokens, cache write tokens, and cache hit rate when present
- repeated prompt-prefix tokens and repeated/similar query count when present

From cost reports, extract:
- Bedrock On-Demand token spend by model
- Provisioned Throughput, model unit, service tier, or reservation charges
- model-specific input/output token rates and any scenario-provided pricing note

## Break-Even Method

Use scenario pricing first. Fall back to AWS Pricing MCP or the pricing page,
then mark calculations as `[estimate]`.

For On-Demand token usage:
```text
on_demand_monthly =
  input_tokens_million  * input_price_per_1m_tokens
+ output_tokens_million * output_price_per_1m_tokens
```

For Provisioned Throughput or committed capacity:
```text
committed_monthly =
  committed_units * hourly_price_per_unit * committed_hours_per_month
```

When the model is priced as a reserved service tier rather than MU-hours, use:
```text
reserved_monthly =
  reserved_tpm_blocks * monthly_price_per_1k_tpm_block
```

Break-even:
```text
monthly_savings = on_demand_monthly - committed_monthly
effective_utilization =
  observed_steady_tokens_per_minute / committed_tokens_per_minute
```

Recommend a commitment only when:
- `monthly_savings > 0`
- traffic is steady enough to use the commitment during most business windows
- p95/p99 latency or throughput needs justify capacity reservation
- the model/region supports the selected commitment mode

For underutilized commitments:
```text
wasted_commitment =
  committed_monthly * max(0, 1 - effective_utilization)
```

## Cache Analysis

### Prompt Caching

Prompt caching fits repeated static prefixes such as system prompts, tool
schemas, policy text, few-shot examples, or large document context.

Required evidence:
- repeated prefix tokens per request
- repeated request count
- current cache read/write token counts, or explicit absence
- model support for prompt caching

Savings:
```text
uncached_repeated_input_cost =
  repeated_prefix_tokens_million * standard_input_price_per_1m

cached_repeated_input_cost =
  cache_write_tokens_million * cache_write_price_per_1m
+ cache_read_tokens_million  * cache_read_price_per_1m

prompt_cache_savings =
  uncached_repeated_input_cost - cached_repeated_input_cost
```

If cache read/write pricing is unavailable, estimate from cost_report or state
the pricing gap instead of inventing a discount.

### Semantic Cache

Semantic caching fits repeated or near-duplicate user questions where answer
freshness and personalization can be controlled.

Required evidence:
- query similarity or duplicate-rate metric
- expected cache hit rate at a stated similarity threshold
- embedding cost and cache operating cost, when available
- freshness, PII, tenant-isolation, and invalidation requirements

Savings:
```text
avoidable_llm_cost =
  avoided_requests * avg_bedrock_cost_per_request

semantic_cache_cost =
  embedding_requests * embedding_cost_per_request
+ cache_node_monthly_cost
+ cache_network_and_storage_cost

net_savings = avoidable_llm_cost - semantic_cache_cost
```

Do not count semantic-cache savings when hit rate is unknown; classify as
`Suspected semantic cache opportunity` and recommend instrumentation.

## Optimized Terraform / Implementation

Use Terraform when the remediation is infrastructure:
- add cache storage such as ElastiCache Serverless or provisioned Redis/Valkey
- add CloudWatch dashboards/alarms for token spend, cache hit rate, and latency
- add Bedrock invocation logging when compliant with data handling requirements

Use implementation fragments or review plans when the remediation is app logic:
- prompt cache checkpoint placement
- semantic-cache lookup before model invocation
- response validation and fallback-to-model path

## Preventive Actions

1. Track input tokens, output tokens, latency, errors, and cache hit rate per
   model and route.
2. Alert when Bedrock spend or token rate grows faster than request volume.
3. Re-run break-even whenever model, region, commitment, or traffic mix changes.
4. Require a cache-safety review for semantic cache rollouts.

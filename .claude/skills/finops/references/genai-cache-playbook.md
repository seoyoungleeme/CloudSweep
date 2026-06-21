# GenAI Cache Playbook

Use this playbook when repeated context or repeated user questions drive LLM
inference spend.

## Cache Selection

| Pattern | Preferred Cache | Evidence |
|---------|-----------------|----------|
| Same large system prompt, tools, policy, or document prefix | Bedrock prompt caching | repeated prefix tokens, cacheable static block |
| Same exact question and deterministic answer | Exact response cache | duplicate query rate, stable answer |
| Similar questions with reusable answers | Semantic cache | embedding similarity, expected hit rate |
| HTTP/object origin repeatedly fetched by LLM app | CloudFront/API cache | cache hit rate, origin requests |
| Shared app state across workers | ElastiCache/Redis/Valkey | concurrent callers, invalidation needs |

## Prompt Cache Method

Prompt caching reduces repeated input token cost and latency for cacheable
prompt prefixes. It does not reuse final answers.

```text
prompt_cache_savings =
  uncached_repeated_input_cost
- cache_write_cost
- cache_read_cost
```

Use when:
- repeated prefix is stable
- model supports prompt caching
- cache read/write token metrics can be monitored

Avoid or require review when:
- prefix includes secrets, tenant-specific data, or rapidly changing policy
- prompt changes frequently enough to prevent hits

## Semantic Cache Method

Semantic cache performs an embedding lookup before model invocation and reuses
an answer when similarity and freshness checks pass.

```text
semantic_cache_net_savings =
  avoided_model_invocations
  * avg_model_cost_per_invocation
- embedding_cost
- cache_operating_cost
```

Use when:
- duplicate or similar query rate is measurable
- answer freshness window is acceptable
- tenant isolation and PII handling are defined
- fallback to the model is always available

## Instrumentation

Track:
- cache hit rate
- cache false positive and fallback rate
- p95/p99 latency
- Bedrock input/output tokens avoided
- embedding requests and cost
- answer quality or human escalation rate

If these are missing, report `Suspected cache opportunity` rather than claiming
savings.

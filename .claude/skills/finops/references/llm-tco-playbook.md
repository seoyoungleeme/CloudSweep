# LLM TCO Playbook

Use this playbook when a workload can run on managed API inference
(Bedrock or another token-priced API) or hosted inference (SageMaker endpoint,
EC2 GPU, Inferentia, or Trainium).

## Required Inputs

| Input | Examples |
|-------|----------|
| Demand | requests/month, input tokens, output tokens, p95/p99 TPM, concurrency |
| Quality | model family, context length, latency SLA, safety requirements |
| Managed API price | input/output token rates, prompt cache rates, commitment price |
| Hosted price | instance type, hourly price, accelerators, replicas, storage, network |
| Utilization | batch size, tokens/sec, target utilization, idle windows |
| Operations | deployment, monitoring, patching, model updates, on-call overhead |

## Managed API Cost

```text
api_monthly =
  input_tokens_million  * input_price_per_1m
+ output_tokens_million * output_price_per_1m
+ cache_write_tokens_million * cache_write_price_per_1m
+ cache_read_tokens_million  * cache_read_price_per_1m
+ commitment_or_reserved_capacity
```

Use zero for cache lines only when the workload does not use that cache mode.

## Hosted Inference Cost

```text
hosted_monthly =
  accelerator_instance_hours * instance_hourly_price
+ endpoint_orchestrator_cost
+ storage_cost
+ data_transfer_cost
+ logging_monitoring_cost
+ engineering_ops_cost
- covered_discount
```

For variable demand:
```text
required_instances =
  ceil(peak_tokens_per_second / safe_tokens_per_second_per_instance)

safe_tokens_per_second_per_instance =
  benchmark_tokens_per_second * target_utilization
```

Include idle capacity unless autoscaling or scheduling evidence proves it is
avoidable.

## Break-Even

```text
break_even_monthly_tokens =
  hosted_monthly / blended_api_price_per_token

blended_api_price_per_token =
  (input_token_share * input_price_per_token)
+ (output_token_share * output_price_per_token)
```

Hosted inference is usually easier to justify when:
- traffic is steady and high volume
- model choice can be hosted safely and legally
- team can operate GPU/accelerator infrastructure
- latency and data-residency requirements favor self-hosting
- reservations, Savings Plans, Spot, or scheduling materially reduce compute

Managed API is usually better when:
- traffic is spiky or low volume
- model quality or provider updates are important
- operations capacity is limited
- fast model switching and safety features matter
- cache savings can reduce token volume without owning infrastructure

## Reporting Rules

- Compare monthly and annual TCO, not just unit price.
- State all assumptions: utilization, batch size, model throughput, discount,
  idle hours, and operations cost.
- Show sensitivity: low/base/high traffic or utilization.
- Do not recommend self-hosting without benchmark evidence or a benchmark plan.

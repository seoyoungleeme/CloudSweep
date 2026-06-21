# finops-sagemaker - Detailed Rules

## Parse Infrastructure

From each `aws_sagemaker_endpoint`:
- endpoint name and referenced endpoint configuration.

From each `aws_sagemaker_endpoint_configuration`:
- production variants
- `instance_type`, `initial_instance_count`, `model_name`,
  `variant_name`, accelerator settings, and data capture settings.

From Application Auto Scaling resources:
- `aws_appautoscaling_target` with `service_namespace = "sagemaker"`
- `scalable_dimension = "sagemaker:variant:DesiredInstanceCount"`
- resource ID pattern: `endpoint/<endpoint-name>/variant/<variant-name>`
- target tracking and scheduled scaling policies.

## Analyze Metrics

Per endpoint variant, read:
- `Invocations`, `InvocationsPerInstance`
- `ModelLatency`, `OverheadLatency`
- `CPUUtilization`, `GPUUtilization`, `GPUMemoryUtilization`, memory usage
- `Invocation4XXErrors`, `Invocation5XXErrors`, throttles, queue/backlog metrics

Use p95 and max values for safety. Averages alone are insufficient.

## Target Tracking

SM1 fires when a production variant has fixed instance count and no matching
Application Auto Scaling target/policy.

Recommended Terraform pattern:
```hcl
resource "aws_appautoscaling_target" "endpoint_variant" {
  max_capacity       = 4
  min_capacity       = 1
  resource_id        = "endpoint/<endpoint-name>/variant/<variant-name>"
  scalable_dimension = "sagemaker:variant:DesiredInstanceCount"
  service_namespace  = "sagemaker"
}

resource "aws_appautoscaling_policy" "endpoint_variant_target" {
  name               = "<endpoint-name>-target-tracking"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.endpoint_variant.resource_id
  scalable_dimension = aws_appautoscaling_target.endpoint_variant.scalable_dimension
  service_namespace  = aws_appautoscaling_target.endpoint_variant.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = 70

    predefined_metric_specification {
      predefined_metric_type = "SageMakerVariantInvocationsPerInstance"
    }
  }
}
```

Tune `target_value`, cooldowns, min/max capacity, and metric choice from observed
traffic and latency.

## Scheduled Scaling

SM2 fires when traffic has known business-hour shape and capacity remains fixed
through nights or weekends.

Use scheduled actions to lower capacity during low-traffic windows only when
business SLA permits. For endpoints that require always-on service, keep at
least the minimum safe capacity. For zero-idle workloads, evaluate async,
serverless, batch transform, or endpoint deletion/recreation workflows.

## Safety Checks

Block or downgrade rightsizing when:
- p95/p99 latency is already near SLA
- GPU memory utilization is high
- errors or throttles are present
- model load time makes scale-out too slow for the workload
- endpoint hosts multiple variants with uneven traffic distribution

## Savings Calculation

Use scenario cost first. Otherwise:
```text
endpoint_instance_savings =
  (current_instance_count - target_instance_count)
  * instance_hourly_price
  * hours_reduced_per_month
```

For scheduled scaling:
```text
scheduled_savings =
  reduced_instances
  * instance_hourly_price
  * off_hours_per_month
```

If Savings Plans or private pricing apply, state that list-price savings are an
estimate and effective savings may differ.

## Preventive Actions

1. Require autoscaling targets for production variants with fixed count > 1.
2. Track `InvocationsPerInstance`, latency, GPU utilization, and errors.
3. Review idle GPU endpoints weekly.
4. Evaluate async, serverless, batch, or managed API options for spiky workloads.

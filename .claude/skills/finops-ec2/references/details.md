# finops-ec2 - GPU Scheduling Details

## Accelerator Families

Treat these EC2 instance families as accelerator cost candidates:
- GPU: `g*`, `p*`
- Inferentia: `inf*`
- Trainium: `trn*`
- Previous generation GPU families when present in scenario data

Do not assume every EC2 instance is schedulable. Identify workload role from
tags, names, ASG membership, user data, metrics, and README/task text.

## Parse Infrastructure

From each `aws_instance`, `aws_launch_template`, and `aws_autoscaling_group`:
- instance type and accelerator family
- schedule-related tags such as `Schedule`, `scheduler:enabled`, `office-hours`,
  `StartStop`, or Instance Scheduler tags
- Auto Scaling desired/min/max capacity and scheduled actions
- EBS volumes, EIPs, IAM roles, lifecycle hooks, and user data checkpointing

Detect schedule controls:
- Instance Scheduler on AWS tag convention
- Systems Manager Quick Setup schedule documents
- EventBridge Scheduler or EventBridge rule + Lambda/SSM automation
- ASG scheduled actions
- workload orchestrator controls such as SageMaker, ECS, Batch, or Kubernetes

## Analyze Metrics

Use:
- CPUUtilization and GPUUtilization
- GPUMemoryUtilization
- NetworkIn/Out and disk I/O
- instance state hours by weekday/hour
- job queue or inference request metrics when available

Off-hour waste is stronger when utilization is low during nights/weekends and
the workload has explicit business-hour tags or traffic shape.

## Scheduling Options

1. **Instance Scheduler on AWS**: best for broad tag-based EC2/RDS schedules
   across accounts and Regions.
2. **Systems Manager Quick Setup scheduling**: simplest entry point for start
   and stop schedules on known EC2 fleets.
3. **EventBridge Scheduler + SSM Automation**: precise custom schedule or
   workflow control.
4. **ASG scheduled actions**: use for launch-template based fleets; schedule
   min, max, and desired capacity together.

For production inference, prefer autoscaling or managed inference services over
hard stops unless there is an approved downtime window.

## Savings Calculation

```text
stopped_hours_per_month =
  off_hours_per_week * 4.345

gross_instance_savings =
  instance_count * instance_hourly_price * stopped_hours_per_month

residual_costs =
  ebs_monthly + eip_monthly + snapshot_monthly + scheduler_monthly

net_savings =
  gross_instance_savings - residual_costs
```

When cost_report gives actual EC2 spend, use:
```text
net_savings =
  avg_monthly_ec2_spend * stoppable_hour_ratio - residual_costs
```

## Preventive Actions

1. Require schedule tags for non-production accelerator instances.
2. Alert on GPU instances running outside approved windows.
3. Review idle accelerator cost weekly.
4. Add checkpoint/resume validation to training workload runbooks.
5. Prefer Spot or managed job services for interruptible training.

# EC2 GPU Scheduling Report Template

Use the orchestrator `references/report-template.md` for unified reports.
For EC2 GPU findings, include:

| Field | Required Content |
|-------|------------------|
| Instance or fleet | resource name, instance type, ASG or standalone |
| Workload role | training, dev, notebook, inference, unknown |
| Runtime evidence | running hours, off-hours, utilization, state history |
| Schedule state | scheduler tags, SSM, EventBridge, ASG actions, or missing |
| Recommendation | Instance Scheduler, SSM Quick Setup, EventBridge, ASG schedule, or review |
| Savings | avoided instance-hours minus residual costs |
| Safety | checkpoint, SLA, warm-up, rollback, residual EBS/EIP costs |

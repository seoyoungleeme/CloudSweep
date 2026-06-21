# GENAI-001

Terraform-free GenAI FinOps fixture covering Bedrock model usage, a fixed SageMaker GPU endpoint, and an unscheduled EC2 training GPU.

- `genai_evidence.json` follows `schemas/genai-evidence.schema.json`.
- `cost_report.json` provides service-level monthly spend.
- The current graph should route to domain analysis and detect `bedrock`, `sagemaker`, and `ec2` without `main.tf`.

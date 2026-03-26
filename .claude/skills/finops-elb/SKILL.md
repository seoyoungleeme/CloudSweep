---
name: finops-elb
description: >
  FinOps Analysis Skill — Detects cost waste in AWS Application Load Balancers (ALB/ELB).
  Automatically executes when given a Terraform configuration (main.tf), CloudWatch metrics
  (metrics.json), and an AWS cost report (cost_report.json). Invoke for requests containing
  keywords: "ELB cost", "ALB waste", "load balancer optimization", "FinOps analysis", "unused ELB".
user_invocable: false
---

# FinOps ELB Analysis Skill

## Directory Layout

When this skill is invoked, two directories matter:

| Variable | Path | Purpose |
|----------|------|---------|
| `SKILL_DIR` | Base directory shown at invocation (e.g. `~/.claude/skills/finops-elb`) | Contains `scripts/` and `rules/` bundled with this skill |
| `WORK_DIR` | Current working directory | Contains the input data files to analyze |

---

## Step 1 — Locate Input Files

`WORK_DIR` 전체를 재귀 스캔하여 존재하는 파일을 모두 확인한다.

```bash
find WORK_DIR -type f | sort
```

스캔 결과에서 아래 파일들을 찾는다. 파일명이 일치하면 경로에 관계없이 사용한다:

| File | Description | 없을 때 |
|------|-------------|---------|
| `main.tf` | Terraform — `aws_lb` resource definitions | 분석 불가 — 사용자에게 경로 요청 |
| `metrics.json` | CloudWatch metrics per resource | 해당 섹션 "제공된 데이터에서 확인 불가 — 실제 환경 검증 필요"로 표시 |
| `cost_report.json` | Monthly cost/waste totals | 해당 섹션 "제공된 데이터에서 확인 불가 — 실제 환경 검증 필요"로 표시 |

스캔 후 발견된 파일 목록과 각 파일의 경로를 명시적으로 출력한 뒤 다음 단계로 진행한다.

---

## Step 2 — Run Pipeline Scripts

Use the Bash tool to run the three scripts from `SKILL_DIR/scripts/`, passing the located input file paths. All output files are written to `WORK_DIR`.

```bash
# 1. Parse
python SKILL_DIR/scripts/parser.py \
  --tf   <main.tf path> \
  --metrics <metrics.json path> \
  --cost <cost_report.json path> \
  --out  WORK_DIR/parsed_input.json

# 2. Analyze
python SKILL_DIR/scripts/analyzer.py \
  --input WORK_DIR/parsed_input.json \
  --rules SKILL_DIR/rules/unused_elb.json \
  --out   WORK_DIR/findings.json

# 3. Format
python SKILL_DIR/scripts/formatter.py \
  --findings WORK_DIR/findings.json \
  --out      WORK_DIR/finops_report.md
```

If `python` is not found, try `python3`. If Python is unavailable, fall back to Step 2-alt.

---

## Step 2-alt — Fallback (No Python)

If Python is unavailable, use the Read tool to read the three input files directly and perform
the analysis yourself using the rules below.

**Metrics to compute per resource:**
- `request_count_avg` = sum(values) / len(values)
- `request_count_zero_days` = count of 0s in values
- `active_connection_count_avg` = sum(values) / len(values)

**Cost summary:**
- `avg_total` = mean of all `total` fields in `cost_report.json`
- `avg_waste` = mean of all `waste` fields

**Rules (from `rules/unused_elb.json`):**

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| A | request_count_avg == 0 AND active_connection_count_avg == 0 AND zero_days >= 28 | HIGH | DELETE |
| B | request_count_avg == 0 AND active_connection_count_avg > 0 | MEDIUM | MONITOR |
| C | otherwise | — | (exclude) |

ALB monthly cost = $0.0225 × 730hr = **$16.43** (us-east-1). Annual = $16.43 × 12.

Confidence boost: computed post-analysis using actual HIGH DELETE count — if `abs(avg_waste − alb_monthly_cost × high_delete_count) < 5.0` → confidence = HIGH. Only applied when `active_connection_data_missing = false`.

---

## Step 3 — Deep Architectural Analysis

### 분석 원칙 (반드시 준수)

- **교차 증거 원칙**: 결론은 반드시 `WORK_DIR`에서 발견된 파일들의 교차 증거에만 기반할 것. 단일 파일의 데이터만으로 단정하지 않는다.
- **불확실성 명시 원칙**: 발견된 파일에 없는 정보(예: 파일 자체가 없거나, 해당 필드가 누락된 경우)는 추측하거나 단정하지 말고 반드시 **"제공된 데이터에서 확인 불가 — 실제 환경 검증 필요"** 로 표시한다.
- **범위 제한 원칙**: AWS 콘솔, 실제 인프라, 외부 시스템에 대한 상태는 파일에서 확인된 것 이상으로 서술하지 않는다.

---

Use the Read tool to read `main.tf` and `WORK_DIR/findings.json`. For each finding, analyze the following:

**2.1 Evidence from Infrastructure (Terraform)**
- 총 리소스 수, 문제 리소스 수
- Listener, Target Group, Route53 연결 여부
- Lifecycle policy 정의 여부

**2.2 Evidence from Metrics (30 days)**
- 문제/정상 리소스 샘플 테이블로 비교
- 핵심 패턴 서술 (예: "30일간 request_count = 0")

**2.3 Evidence from Cost Report (6 months)**
- 월별 테이블 (Total, Waste, Waste%)
- 평균 waste 수치 + 서비스별 격리 여부

**2.4 Root Cause**
- 아키텍처 맥락에서 왜 발생했는지 서술
- 단순 "트래픽 없음"이 아니라 인과관계 설명

**Proposed Solution**
- Immediate Actions (즉시 실행 가능한 것)
- Preventive Actions (재발 방지)
- Optimized Terraform 코드 포함

---

## Step 4 — Write Final Report

Use the Write tool to save `WORK_DIR/finops_report.md`, then output the full report in your response.

### Report format:

```
# FinOps ELB Deep Analysis Report — <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Unused ALB |
| Affected Resources | X of Y aws_lb |
| Monthly Waste | $XX |
| Waste Percentage | ~X% |

## Root Cause

### 2.1 Evidence from Infrastructure (Terraform)
<분석 내용>

### 2.2 Evidence from Metrics (CloudWatch — 30 days)
| Resource | Request Avg | Conn Avg | is_problem |
|----------|-------------|----------|------------|
| lb-xxx   | 0           | 0        | ✅ Yes     |

### 2.3 Evidence from Cost Report (6 months)
| Month | Total | Waste | Waste% |
|-------|-------|-------|--------|

### 2.4 Root Cause
<아키텍처 기반 원인>

## Proposed Solution

### Immediate Actions (Week 1)
1. ...

### Preventive Actions (Week 2-4)
1. ...

## Estimated Monthly Savings (USD)
$XX.XX

## Optimized Terraform

**생성 원칙**: 입력으로 받은 실제 `main.tf` 파일을 기반으로 수정된 버전을 생성한다.
플레이스홀더(`<resource-name>` 등)를 사용하지 말 것. 실제 리소스명, 실제 값을 그대로 사용한다.
완성된 코드는 `WORK_DIR/main_optimized.tf`로 저장하고 리포트에도 포함한다.

### 삭제 전 안전 검증 순서 (반드시 이 순서로 실행)
```bash
# Step 1. Route53 / 외부 DNS에서 해당 ALB DNS명 참조 여부 확인
#   aws elbv2 describe-load-balancers --names <실제 lb 이름들> \
#     --query 'LoadBalancers[*].DNSName'
#   → 반환된 DNS명을 Route53 및 외부 DNS에서 검색

# Step 2. Listener 없음 재확인
#   aws elbv2 describe-listeners --load-balancer-arn <ARN>
#   → 결과가 비어 있어야 삭제 진행 가능

# Step 3. 변경사항 사전 검토
#   terraform plan -out=cleanup.plan

# Step 4. plan 검토 후 수동 적용
#   terraform apply cleanup.plan
```

아래는 실제 `main.tf` 기반으로 생성된 수정본의 구조 예시다.
실제 리포트에서는 이 구조를 따르되 내용은 발견된 파일의 실제 리소스명/값으로 채운다:

```hcl
# (원본 main.tf의 terraform {}, provider {} 블록 그대로 유지)

# ──────────────────────────────────────────────
# 삭제 대상 ALB — [실제 리소스명]
# 삭제 전 위 안전 검증 순서 완료 필수
# 제거 이유: <기간>일간 request_count = 0, active_connection = 0
#            $<금액>/월 고정 비용 낭비 (findings.json 기준)
# 후속 작업: ALB 삭제 후 연결된 SG(<실제 SG 참조명>) 별도 삭제
# ──────────────────────────────────────────────
# resource "aws_lb" "<실제 리소스명>" { ... 원본 블록 그대로 ... }

# ──────────────────────────────────────────────
# 유지 대상 ALB — [실제 리소스명]
# 주의: aws_lb_listener 없이 ALB만 존재하면 트래픽 수신 불가.
#       반드시 aws_lb_listener 리소스와 함께 운영할 것.
# ──────────────────────────────────────────────
resource "aws_lb" "<실제 리소스명>" {
  # 원본 속성 그대로 유지
  name               = "<원본 name값>"
  ...

  # FinOps 개선: 안전 속성 추가
  enable_deletion_protection = true  # 실수 삭제 방지
  idle_timeout               = 60    # 기본값 명시 (초)

  tags = {
    # 원본 태그 유지 + 필수 태그 추가
    Name        = "<원본 Name값>"
    Environment = var.environment
    Owner       = var.owner
    CreatedFor  = var.created_for
    ManagedBy   = "terraform"
  }
}
```

---

### 선택적 적용 — Cost Anomaly Detection

> 아래 리소스는 선택적으로 적용한다. 적용 전 `terraform plan` 먼저 실행할 것.

```hcl
resource "aws_ce_anomaly_monitor" "elb_monitor" {
  name              = "elb-anomaly-monitor"
  monitor_type      = "DIMENSIONAL"
  monitor_dimension = "SERVICE"
}

resource "aws_ce_anomaly_subscription" "elb_alert" {
  name      = "elb-anomaly-alert"
  frequency = "DAILY"

  monitor_arn_list = [aws_ce_anomaly_monitor.elb_monitor.arn]

  subscriber {
    type    = "EMAIL"
    address = var.finops_alert_email
  }

  threshold_expression {
    dimension {
      key           = "ANOMALY_TOTAL_IMPACT_ABSOLUTE"
      values        = ["10"]
      match_options = ["GREATER_THAN_OR_EQUAL"]
    }
  }
}
```

---

### 선택적 적용 — AWS Config Rule (태그 강제)

> 아래 리소스는 선택적으로 적용한다. 적용 전 `terraform plan` 먼저 실행할 것.

```hcl
resource "aws_config_config_rule" "elb_required_tags" {
  name = "elb-required-tags"

  source {
    owner             = "AWS"
    source_identifier = "REQUIRED_TAGS"
  }

  input_parameters = jsonencode({
    tag1Key = "Owner"
    tag2Key = "Environment"
    tag3Key = "CreatedFor"
  })

  scope {
    compliance_resource_types = ["AWS::ElasticLoadBalancingV2::LoadBalancer"]
  }
}
```

---
*Generated by: finops-elb skill — Claude Code*
```

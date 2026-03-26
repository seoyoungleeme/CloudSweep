# FinOps ELB Deep Analysis Report — L1-005

## Problem Identification

| Category | Details |
|----------|---------|
| Waste Type | Unused ALB (Application Load Balancer) |
| Affected Resources | 2 of 3 `aws_lb` |
| Region | us-east-1 (main.tf 확인) |
| Confirmed Monthly Waste | $32.86 |
| Confirmed Annual Waste | $394.32 |
| Avg Monthly Cloud Spend | $213.97 |
| Avg Monthly Waste | $33.21 (15.5% of total) |
| Confidence | HIGH |

> **데이터 범위**: 분석은 `main.tf`, `metrics.json`, `cost_report.json` 3개 파일의 교차 증거에만 기반함.

---

## Root Cause

### 2.1 Evidence from Infrastructure (Terraform)

**`main.tf`에서 확인된 사실:**

| 항목 | 확인 내용 |
|------|-----------|
| 총 `aws_lb` 리소스 수 | 3개 |
| 문제 리소스 수 | 2개 (`lb-4dzo8v`, `lb-ucc4pu`) |
| load_balancer_type | 3개 모두 `application` |
| internal | 3개 모두 `false` (인터넷 facing) |
| `aws_lb_listener` 정의 | **없음** — `main.tf` 내 미존재 |
| `aws_lb_target_group` 정의 | **없음** — `main.tf` 내 미존재 |
| `aws_route53_record` 정의 | **없음** — `main.tf` 내 미존재 |
| Lifecycle policy | **없음** — `main.tf` 내 미존재 |
| `Owner`, `Environment` 태그 | **없음** — `Name` 태그만 존재 |

> **제공된 데이터에서 확인 불가 — 실제 환경 검증 필요**:
> - 다른 `.tf` 파일에 Listener/Target Group이 정의되어 있을 가능성
> - AWS 콘솔에서 직접 생성된 Route53 레코드 존재 여부
> - 실제 ALB ARN 및 DNS명

### 2.2 Evidence from Metrics (CloudWatch — 30 days)

**`metrics.json`에서 확인된 사실:**

| Resource | Request Avg | Request Zero Days | Conn Avg | Conn Zero Days | Status |
|----------|-------------|-------------------|----------|----------------|--------|
| lb-4dzo8v | 0.0 | 30 / 30 | 0.0 | 30 / 30 | PROBLEM (HIGH) |
| lb-ucc4pu | 0.0 | 30 / 30 | 0.0 | 30 / 30 | PROBLEM (HIGH) |
| lb-ffxzco | 100.0 | 0 / 30 | 49.9 | 0 / 30 | NORMAL |

- `lb-4dzo8v`, `lb-ucc4pu`: 30일 전체에서 request_count, active_connection_count 모두 절대 0
- `lb-ffxzco`: request avg 100/hr, connection avg 49.9로 정상 운영 중 → 모니터링 인프라 정상 확인

> **제공된 데이터에서 확인 불가 — 실제 환경 검증 필요**:
> - 메트릭 수집 기간은 30일. 30일 이전 트래픽 이력
> - Health check 전용 트래픽 여부 (CloudWatch Logs 필요)

### 2.3 Evidence from Cost Report (6 months)

**`cost_report.json`에서 확인된 사실:**

| Month | Total Spend | ELB Spend | Waste | Waste % |
|-------|-------------|-----------|-------|---------|
| M-5 | $214.44 | $45.64 | $32.73 | 15.3% |
| M-4 | $217.65 | $36.26 | $33.24 | 15.3% |
| M-3 | $222.94 | $49.48 | $34.07 | 15.3% |
| M-2 | $202.80 | $47.08 | $32.21 | 15.9% |
| M-1 | $201.96 | $37.98 | $33.97 | 16.8% |
| M-0 | $224.04 | $48.25 | $33.05 | 14.8% |
| **Avg** | **$213.97** | **$44.12** | **$33.21** | **15.5%** |

- 6개월 내내 waste ~$33/월로 일정 지속 (최소 $32.21 ~ 최대 $34.07)
- cost_report는 ELB 서비스 전체의 waste를 기록 (리소스별 분리 없음)
- 추정 절감액 $32.86 vs avg_waste $33.21 → delta $0.35 이내 — **교차 증거 일치**

> **제공된 데이터에서 확인 불가 — 실제 환경 검증 필요**:
> - cost_report의 waste가 `lb-4dzo8v`, `lb-ucc4pu` 각각에서 얼마씩 발생했는지 (리소스별 분리 데이터 없음)
> - 6개월 이전 이력

### 2.4 Root Cause

**3개 파일 교차 증거 기반 결론:**

1. `main.tf` 확인: `lb-4dzo8v`, `lb-ucc4pu`에 Listener/Target Group 없음 → 트래픽 수신 경로 부재
2. `metrics.json` 확인: 동 리소스에서 30일간 request_count = 0, connection = 0 → 실제로 트래픽 없음
3. `cost_report.json` 확인: 6개월간 ELB waste $32~34/월 지속 → 추정 ALB 고정비($32.85)와 일치

세 파일의 증거가 모두 같은 방향을 가리킴: **Listener 없이 프로비저닝된 ALB가 방치되어 고정 비용만 발생 중.**

방치 원인: 제공된 파일만으로는 확정 불가. `terraform destroy` 불완전 실행, 테스트 환경 정리 누락 등이 가능한 시나리오이나 **제공된 데이터에서 확인 불가 — 실제 환경 검증 필요**.

---

## Proposed Solution

### Immediate Actions (Week 1)

1. **삭제 전 외부 DNS 참조 확인** (파일에 DNS 정보 없음 — 실제 환경 확인 필수):
   ```bash
   aws elbv2 describe-load-balancers --names lb-4dzo8v lb-ucc4pu \
     --query 'LoadBalancers[*].{Name:LoadBalancerName,ARN:LoadBalancerArn,DNS:DNSName}'
   ```

2. **Listener 없음 재확인** (`main.tf`에 없으나 다른 TF 파일 또는 콘솔 생성 가능성 배제):
   ```bash
   aws elbv2 describe-listeners --load-balancer-arn <ARN_lb-4dzo8v>
   aws elbv2 describe-listeners --load-balancer-arn <ARN_lb-ucc4pu>
   ```

3. **Terraform으로 삭제:**
   ```bash
   terraform plan -out=cleanup.plan
   terraform apply cleanup.plan
   ```

4. **고아 Security Group 후속 정리** (ALB 삭제 완료 후):
   ```bash
   aws ec2 delete-security-group --group-name lb-4dzo8v_sg
   aws ec2 delete-security-group --group-name lb-ucc4pu_sg
   ```

### Preventive Actions (Week 2–4)

1. **Listener 의존성 강제** — ALB 모듈에서 `aws_lb_listener`를 필수 입력으로 요구.
2. **태그 필수화** — `Owner`, `Environment`, `CreatedFor` 3개 태그 없는 ALB 생성 차단.
3. **Cost Anomaly Detection 설정** — ELB 지출 이상 감지 시 알림.
4. **월간 FinOps 스캔 예약** — 이 skill을 월 1회 실행.

---

## Estimated Monthly Savings (USD)

| Resource | Action | Type | Monthly | Annual |
|----------|--------|------|---------|--------|
| lb-4dzo8v | DELETE | Confirmed | $16.43 | $197.16 |
| lb-ucc4pu | DELETE | Confirmed | $16.43 | $197.16 |
| **Total** | | | **$32.86** | **$394.32** |

> Cost basis: $0.0225/hr × 730hr = $16.43/month per ALB (us-east-1). LCU = $0 (no traffic).

---

## Optimized Terraform

### 삭제 전 안전 검증 순서 (반드시 이 순서로 실행)

```bash
# Step 1. Route53 / 외부 DNS에서 해당 ALB DNS명 참조 여부 확인
#   aws elbv2 describe-load-balancers --names lb-4dzo8v lb-ucc4pu \
#     --query 'LoadBalancers[*].DNSName'

# Step 2. Listener 없음 재확인
#   aws elbv2 describe-listeners --load-balancer-arn <ARN>

# Step 3. 변경사항 사전 검토
#   terraform plan -out=cleanup.plan

# Step 4. plan 검토 후 수동 적용
#   terraform apply cleanup.plan
```

```hcl
# ──────────────────────────────────────────────
# 삭제 대상 ALB (위 안전 검증 완료 후 제거)
# ──────────────────────────────────────────────
# resource "aws_lb" "lb-4dzo8v" { ... }
# → 제거 이유: 30일 request_count = 0, active_connection = 0, $16.43/월 낭비

# resource "aws_lb" "lb-ucc4pu" { ... }
# → 제거 이유: 동일

# ──────────────────────────────────────────────
# 고아 Security Group 정리 (ALB 삭제 완료 후 별도 단계로 실행)
# ──────────────────────────────────────────────
# resource "aws_security_group" "lb-4dzo8v_sg" { ... }  # 삭제
# resource "aws_security_group" "lb-ucc4pu_sg" { ... }  # 삭제

# ──────────────────────────────────────────────
# 유지 대상 ALB
# 주의: aws_lb_listener 없이 ALB만 존재하면 트래픽 수신 불가.
# ──────────────────────────────────────────────
resource "aws_lb" "lb-ffxzco" {
  name               = "lb-ffxzco"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.lb-ffxzco_sg.id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = true
  idle_timeout               = 60

  tags = {
    Name        = "lb-ffxzco"
    Environment = var.environment
    Owner       = var.owner
    CreatedFor  = var.created_for
    ManagedBy   = "terraform"
  }
}
```

---

### 선택적 적용 — Cost Anomaly Detection

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

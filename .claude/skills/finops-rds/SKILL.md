---
name: finops-rds
description: >
  FinOps Analysis Skill — Detects cost waste in AWS RDS instances.
  Covers two categories: (R1) Multi-AZ enabled on non-production environments,
  and (R2) chronically under-utilized instance classes.
  Automatically executes when given a Terraform configuration (main.tf),
  CloudWatch metrics (metrics.json), and an AWS cost report (cost_report.json).
  Keywords: "RDS cost", "RDS overprovisioning", "Multi-AZ dev", "database optimization", "FinOps RDS".
user_invocable: false
---

# FinOps RDS Analysis Skill

## Directory Layout

| Variable | Path | Purpose |
|----------|------|---------|
| `SKILL_DIR` | Base directory of this skill (e.g. `.claude/skills/finops-rds`) | Contains `scripts/` and `rules/` |
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
| `main.tf` | Terraform — `aws_db_instance` resource definitions | 분석 불가 — 사용자에게 경로 요청 |
| `metrics.json` | CloudWatch metrics per resource (cpu_utilization, database_connections) | 해당 섹션 "제공된 데이터에서 확인 불가 — 실제 환경 검증 필요"로 표시 |
| `cost_report.json` | Monthly RDS cost history | 해당 섹션 "제공된 데이터에서 확인 불가 — 실제 환경 검증 필요"로 표시 |

스캔 후 발견된 파일 목록과 각 파일의 경로를 명시적으로 출력한 뒤 다음 단계로 진행한다.

---

## Step 2 — Run Pipeline Scripts

Use the Bash tool to run the three scripts from `SKILL_DIR/scripts/`.

```bash
# 1. Parse
python SKILL_DIR/scripts/parser.py \
  --tf      <main.tf path> \
  --metrics <metrics.json path> \
  --cost    <cost_report.json path> \
  --out     WORK_DIR/parsed_input.json

# 2. Analyze
python SKILL_DIR/scripts/analyzer.py \
  --input WORK_DIR/parsed_input.json \
  --rules SKILL_DIR/rules/overprovisioned_rds.json \
  --out   WORK_DIR/findings.json

# 3. Format
python SKILL_DIR/scripts/formatter.py \
  --findings WORK_DIR/findings.json \
  --out      WORK_DIR/finops_report.md
```

If `python` is not found, try `python3`. If Python is unavailable, fall back to Step 2-alt.

---

## Step 2-alt — Fallback (No Python)

If Python is unavailable, read all three input files with the Read tool and apply the rules below manually.

**Metrics to compute per resource** (from `metrics.json`):
- `cpu_utilization_avg` = mean of all datapoints
- `database_connections_avg` = mean of all datapoints

**Terraform fields to read** (from `main.tf` per `aws_db_instance`):
- `instance_class`
- `multi_az`
- `tags.Environment`

**Rules:**

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| R1 | `multi_az = true` AND `Environment` tag ∈ {dev, test, staging, sandbox} | HIGH | DISABLE_MULTI_AZ |
| R2 | `cpu_utilization_avg < 20%` AND DB has connections | MEDIUM | DOWNSIZE |

**Savings calculation:**
- R1: `single_az_hourly × 730hr` (the cost of the redundant AZ eliminated)
- R2: `(current_hourly − recommended_hourly) × 730hr × az_multiplier`
  - `az_multiplier` = 2 if multi_az else 1
- `db.r5.large` us-east-1: $0.24/hr single-AZ → $175.20/mo; Multi-AZ → $350.40/mo
- Downsize `db.r5.large` → `db.t3.large` ($0.136/hr → $99.28/mo)

---

## Step 3 — Deep Architectural Analysis

### 분석 원칙 (반드시 준수)

- **교차 증거 원칙**: 결론은 반드시 발견된 파일들의 교차 증거에만 기반할 것.
- **불확실성 명시 원칙**: 제공된 파일에 없는 정보는 **"제공된 데이터에서 확인 불가 — 실제 환경 검증 필요"** 로 표시한다.
- **범위 제한 원칙**: 파일에서 확인된 것 이상으로 서술하지 않는다.

Use the Read tool to read `main.tf` and `WORK_DIR/findings.json`. For each finding, analyze:

**3.1 Evidence from Infrastructure (Terraform)**
- 총 aws_db_instance 수, 문제 리소스 수
- 각 인스턴스의 `instance_class`, `multi_az`, `Environment` 태그 요약
- 운영/개발 구분 현황

**3.2 Evidence from Metrics (30 days)**
- 리소스별 CPU 평균, DB Connection 평균 비교표
- 이상 패턴 서술

**3.3 Evidence from Cost Report (6 months)**
- 월별 RDS 비용 추세
- `pricing_note` 등 메타 정보 활용

**3.4 Root Cause**
- 아키텍처/운영 프로세스 관점에서 왜 이 낭비가 발생했는지 설명

**Proposed Solution**
- Immediate Actions (즉시 실행 가능)
- Preventive Actions (재발 방지)
- Optimized Terraform 코드 포함

**Optimized Terraform 생성 규칙**:
- 입력으로 받은 실제 `main.tf` 파일을 기반으로 수정된 버전을 생성한다.
- 플레이스홀더(`<resource-name>` 등)를 사용하지 말 것. 실제 리소스명, 실제 값을 그대로 사용한다.
- R1(Multi-AZ 비활성화): `multi_az = false` 로 변경하고, 변경 이유를 인라인 주석으로 명시한다.
- R2(인스턴스 다운사이즈): `instance_class`를 권장 클래스로 변경하고, 변경 이유를 인라인 주석으로 명시한다.
- 변경이 없는 리소스는 원본 그대로 유지한다.
- 완성된 코드는 Write 툴로 `WORK_DIR/main_optimized.tf`로 저장하고 리포트에도 포함한다.

---

## Step 4 — Write Final Report

Use the Write tool to save `WORK_DIR/finops_report.md`, then output the full report in the response.

> **주의**: `finops_report.md`와 `main_optimized.tf` 두 파일 모두 Write 툴로 저장해야 한다.

### Report format:

```
# FinOps RDS Deep Analysis Report — <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Types | Multi-AZ on Dev, CPU Overprovisioning |
| Affected Resources | X of Y aws_db_instance |
| Monthly Waste | $XX |

## Root Cause

### 3.1 Evidence from Infrastructure (Terraform)
<분석 내용>

### 3.2 Evidence from Metrics (CloudWatch — 30 days)
| Resource | CPU Avg | DB Connections Avg | Issue |
|----------|---------|-------------------|-------|

### 3.3 Evidence from Cost Report (6 months)
| Month | RDS Spend | Total Spend |
|-------|-----------|-------------|

### 3.4 Root Cause
<아키텍처 기반 원인>

## Proposed Solution

### Immediate Actions (Week 1)
1. ...

### Preventive Actions (Week 2-4)
1. ...

## Estimated Monthly Savings (USD)
$XX.XX

## Optimized Terraform
<실제 리소스명 기반 수정본>
```

---

*Generated by: finops-rds skill — Claude Code*

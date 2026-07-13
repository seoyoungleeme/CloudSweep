# CloudSweep

CloudSweep는 AWS 비용 낭비와 비용 이상 징후를 분석하는 LangGraph 기반 FinOps 도구다.

Terraform, CloudWatch 지표, 비용 보고서, Cost Explorer, CloudTrail, GenAI 사용량을 함께 읽어 다음 산출물을 만든다.

- 서비스별 비용 최적화 finding
- 재현 가능한 절감액과 evidence fact
- 서비스 간 의존성, 요청 증폭, 비용 spike 분석
- 검토용 Terraform 변경 후보
- AI review와 report polish가 반영된 최종 보고서

CloudSweep는 AWS 리소스나 Terraform을 직접 변경하지 않는다. 모든 Terraform 결과물은 검토용 후보 파일이다.

## 빠른 시작

```powershell
pip install -r requirements.txt

# 결과 파일을 쓰지 않고 분석만 수행
python -m cloudsweep sample\season2\MA-001 --dry-run

# 기본 CLI 출력명으로 result/ 아래에 분석 결과 생성
python -m cloudsweep sample\season2\MA-001

# /finops 완료 산출물과 같은 이름으로 생성
python -m cloudsweep sample\season2\MA-001 --standard-output

# 전체 테스트
python -m unittest discover -s tests -v
```

현재 확인한 샘플 dry-run 출력:

```text
Intent: waste_optimization
Plan: domain_analysis -> report
Domains: lambda, s3, dynamodb
Findings: 6
AI review requested: result/.machine/ai_review_request.json
Dry run: no files written.
```

현재 테스트 상태:

```text
Ran 73 tests
OK
```

## 실행 진입점

### CLI

기본 실행 명령은 다음과 같다.

```powershell
python -m cloudsweep <WORK_DIR>
```

지원 옵션:

| 옵션 | 동작 |
|------|------|
| `--dry-run` | LangGraph를 실행하지만 graph 결과 파일은 쓰지 않는다. |
| `--standard-output` | `result/finops_report.md`, `result/main_optimized.tf` 이름으로 쓴다. |
| `--from-ministack` | graph 실행 전 MiniStack에서 읽기 전용 evidence를 수집한다. |
| `--collect-only` | MiniStack evidence만 수집하고 graph 분석은 건너뛴다. `--from-ministack` 필요. |

MiniStack evidence만 준비할 때:

```powershell
python -m cloudsweep <WORK_DIR> --from-ministack --collect-only
```

MiniStack 수집은 `main.tf`, `metrics.json`, `parsed_input.json`을 생성한다. `--from-ministack --dry-run`을 함께 쓰면 evidence 파일은 생성되고 graph 결과 파일만 생성되지 않는다.

### `/finops`

Claude Code에서는 `.claude/skills/finops/SKILL.md`의 `/finops`가 오케스트레이터 역할을 한다. `/finops`는 CLI를 한 번 실행하고 끝내는 흐름이 아니라, machine request 파일을 보고 필요한 보강 파일을 작성한 뒤 LangGraph를 여러 번 재실행하는 프로세스다.

최종 완료 산출물은 다음 이름을 기준으로 한다.

```text
<WORK_DIR>/result/finops_report.md
<WORK_DIR>/result/main_optimized.tf
```

CLI만 단독으로 실행하면 기본 출력명은 다음처럼 graph 전용 이름이다.

```text
<WORK_DIR>/result/cloudsweep_graph_report.md
<WORK_DIR>/result/cloudsweep_main_optimized.tf
```

`--standard-output`을 사용하면 CLI도 `/finops` 최종 산출물과 같은 이름으로 쓴다.

### Legacy finalize

과거 `claude_review.json` 기반 finalize 경로도 남아 있다. 현재 `/finops` 흐름과는 별도이며, 일반 실행에서는 사용하지 않는다.

```powershell
python -m cloudsweep finalize <WORK_DIR> --review <path-to-review.json>
```

`--review` 파일은 `schemas/claude-review.schema.json` 계약을 따른다. 출력은 `result/.machine/` 아래에 격리되며 기본 보고서를 덮어쓰지 않는다.

## 실행 프로세스

CloudSweep의 LangGraph 흐름은 다음 순서로 돈다.

1. `WORK_DIR`에서 evidence를 inventory한다.
2. evidence 종류에 따라 `cost_spike_incident`, `waste_optimization`, `blended` 같은 intent와 실행 계획을 정한다.
3. Cost Explorer 또는 anomaly evidence가 있으면 anomaly workflow를 먼저 수행한다.
4. Terraform, metrics, parsed input, cost report, GenAI evidence에서 분석 도메인을 탐지한다.
5. 탐지된 도메인마다 analyzer를 fan-out으로 실행한다.
6. pricing, documentation enrichment를 적용한다. 기본 CLI는 로컬 fallback provider를 사용한다.
7. 필요한 경우 approval gate, cross-domain review, AI review request, report polish request를 거친다.
8. report와 Terraform 후보, machine state, pending request 파일을 렌더링한다.

파일 기준으로 보면 핵심 상태는 항상 아래에 모인다.

```text
<WORK_DIR>/result/
  cloudsweep_graph_report.md          # 기본 CLI report
  cloudsweep_main_optimized.tf        # 기본 CLI Terraform 후보
  finops_report.md                    # --standard-output 또는 /finops 최종 report
  main_optimized.tf                   # --standard-output 또는 /finops 최종 Terraform 후보
  .machine/
    cloudsweep_graph_state.json
    {domain}_skill_request.json
    {domain}_pricing_request.json
    ai_review_request.json
    ai_review.json
    report_polish_request.json
    report_polish.json
    token_usage.json
```

`result/.machine/cloudsweep_graph_state.json`에는 run id, intent, execution plan, domains, analyzer coverage, findings, evidence facts, dependency facts, request 파일 경로, warning, trace가 기록된다.

## `/finops` 반복 실행 흐름

`/finops`는 다음 파일이 생겼는지 확인하면서 LangGraph를 재실행한다.

1. `python -m cloudsweep <WORK_DIR> --standard-output`으로 1차 분석을 수행한다.
2. 복잡 도메인이 있으면 `result/.machine/{domain}_skill_request.json`이 생성된다.
3. public pricing이 필요하면 `result/.machine/{domain}_pricing_request.json`이 생성된다.
4. pricing request가 있으면 AWS public on-demand 단가를 조회해 repo root의 `pricing_cache/{domain}_pricing_model.json`에 병합한다.
5. `rds`, `elb`, `ecs`, `elasticache` request가 있으면 해당 도메인 Skill이 `result/.machine/{domain}_skill_analysis.json`을 작성한다.
6. LangGraph를 재실행해 Skill 결과와 pricing cache를 반영한다.
7. `ai_review_request.json`이 있으면 `schemas/ai-review.schema.json`에 맞춰 `ai_review.json`을 작성한다.
8. LangGraph를 재실행한다.
9. `report_polish_request.json`이 있으면 `schemas/report-polish.schema.json`에 맞춰 `report_polish.json`을 작성한다.
10. LangGraph를 마지막으로 재실행해 `finops_report.md`와 `main_optimized.tf`에 반영한다.

복잡 도메인의 Skill 출력:

| 도메인 | Skill | 출력 파일 |
|--------|-------|-----------|
| RDS | `finops-rds` | `result/.machine/rds_skill_analysis.json` |
| ELB | `finops-elb` | `result/.machine/elb_skill_analysis.json` |
| ECS | `finops-ecs` | `result/.machine/ecs_skill_analysis.json` |
| ElastiCache | `finops-elasticache` | `result/.machine/elasticache_skill_analysis.json` |

복잡 도메인은 request 번들만으로 절감액을 추정하지 않는다. Skill analysis 파일이 없으면 해당 복잡 도메인은 finding을 만들지 않고 request 파일만 남긴다.

## 분석 책임

CloudSweep는 도메인 성격에 따라 분석 책임을 나눈다.

| 유형 | 도메인 | 분석 주체 |
|------|--------|-----------|
| 단순 정책, RuleEngine | cloudwatch, cloudwatch-alarm, sqs, kinesis, ebs, nat, tgw, organizations | Rule v2 JSON + `RuleEngine` |
| 단순 정책, Python 직접 | lambda, s3, dynamodb | Python analyzer |
| GenAI | bedrock, sagemaker, ec2 | Python rich analyzer, `genai_evidence.json` |
| 복잡 판단형 | rds, elb, ecs, elasticache | LangGraph evidence bundle + Claude domain Skill |
| 비용 이상 | Cost Explorer, anomaly, CloudTrail | LangGraph anomaly workflow |

단순 및 GenAI 도메인은 Python analyzer 또는 Rule v2 JSON이 탐지, threshold, 절감액 계산, Terraform 후보를 책임진다. Claude는 reviewer 역할만 한다.

복잡 도메인은 LangGraph가 Terraform, metrics, cost, parsed input을 구조화해 Skill request를 만들고, 도메인 Skill이 finding 자체를 작성한다. LangGraph는 이후 finding id, evidence fact, savings group, cross-domain note를 보강한다.

Public pricing은 별도 보강 흐름이다. `cost_report.json`이 없거나 단가를 resolve할 수 없으면 `result/.machine/{domain}_pricing_request.json`이 생성된다. 조회한 단가는 scenario 내부가 아니라 repo root의 `pricing_cache/{domain}_pricing_model.json`에 병합한다. 이 캐시는 여러 scenario가 공유한다.

## 전체 구조

![CloudSweep 전체 분석 로직 구조](cloudsweep_architecture.png)

도메인 분석 방식:

![도메인 분석 방식](arch_2_domains.png)

실행 파이프라인:

![CloudSweep 분석 실행 파이프라인](arch_1_pipeline.png)

Rule v2 predicate와 blocker 구조:

![Rule v2 predicate와 blocker 구조](arch_3_rules.png)

## 입력 Evidence

분석에 필요한 파일만 `WORK_DIR` 아래에 제공하면 된다.

| Evidence | 기본 경로 | 용도 |
|----------|-----------|------|
| Terraform | `main.tf` | 리소스, 설정, 참조 관계, Terraform 후보 |
| Metrics | `metrics.json`, `metrics/metrics.json` | 평균, p95/p99, 오류, throttling, lag |
| Cost report | `cost_report.json` | 서비스 및 리소스 비용, 단가 근거 |
| Parsed input | `parsed_input.json` | 기존 수집기의 구조화 evidence |
| GenAI usage | `genai_evidence.json` | token, cache, endpoint, accelerator 비용 |
| Cost Explorer | `mock_responses/get_cost_and_usage*.json` | 비용 spike와 서비스 attribution |
| Cost anomaly | `mock_responses/get_anomalies.json` | 이상 비용 확인과 영향 범위 |
| CloudTrail | `mock_responses/cloudtrail*.json`, `cloudtrail.json` | triggering event 시간 상관관계 |
| Complex Skill output | `result/.machine/{domain}_skill_analysis.json` | 복잡 도메인의 선행 분석 결과 |

필수 evidence가 부족하면 finding을 억지로 확정하지 않고 confidence를 낮추거나 evidence gap을 남긴다.

## 저장소 구조

```text
.claude/skills/
  finops/                         # /finops 오케스트레이터
  finops-anomaly/                 # anomaly 분석 Skill 문서
  finops-*/SKILL.md               # 도메인별 검토 또는 복잡 도메인 분석 계약
  finops-*/references/*.md        # 도메인별 분석 및 보고 참고 문서
  finops-*/rules/*.json           # Rule v2 정책 파일

cloudsweep/
  __main__.py                     # python -m cloudsweep 진입점
  graph.py                        # LangGraph state, nodes, CLI parser, fan-out, render flow
  domain_detection.py             # evidence 기반 도메인 탐지
  domain_analyzers.py             # 18개 도메인 analyzer와 registry
  rule_engine.py                  # Rule v2 predicate, validation, handler 실행
  complex_domains.py              # rds/elb/ecs/elasticache Skill request 및 output 처리
  pricing_models.py               # shared pricing cache loader/request builder
  enrichment.py                   # pricing/docs enrichment provider와 fallback
  anomaly.py                      # Cost Explorer/CloudTrail 기반 anomaly 분석
  cross_domain.py                 # cross-domain fact와 hypothesis 생성
  ai_review.py                    # AI review/report polish request 및 response loader
  reporting.py                    # Markdown report와 Terraform 후보 렌더링
  token_usage.py                  # Claude Code transcript 기반 token/cost 집계
  finalizer.py                    # legacy claude-review finalize 경로
  ministack_collector.py          # 읽기 전용 MiniStack evidence 수집기

schemas/
  finops-rule-v2.schema.json
  skill-analysis.schema.json
  pricing-model.schema.json
  ai-review.schema.json
  report-polish.schema.json
  claude-review.schema.json
  genai-evidence.schema.json

pricing_cache/
  lambda_pricing_model.json       # shared public-pricing cache
  rds_pricing_model.json

sample/
  season1/                        # 단일/복합 서비스 회귀 fixture
  season2/
    MA-001/                       # Lambda + S3 + DynamoDB
    GENAI-001/                    # Bedrock + SageMaker + EC2
    LV-001/                       # Cost anomaly workflow
    XS-001/                       # 작은 multi-domain fixture
    assignment.json

lab01/
  main.tf
  metrics.json
  parsed_input.json
  result/                         # 실행 결과 예시

tests/
  test_all_domains.py
  test_cross_domain.py
  test_finalizer.py
  test_genai_analyzers.py
  test_graph_architecture.py
  test_graph_smoke.py
  test_ministack_collector.py
  test_pricing_models.py
  test_rule_engine.py
  test_token_usage.py

ARCHITECTURE.md                   # LangGraph runtime과 배포 adapter 구조
RULE_CATALOG.md                   # Rule v2 전체 분류표
FINAL_REPORT.md                   # 프로젝트 결과 정리
requirements.txt                  # runtime dependency
```

루트의 `0511.md`, `0518.md`, `0525.md`, `0601.md`, `0615.md`, `0622.md`는 구현 과정 기록이다. `gen_diagram.py`, `gen_diagrams.py`는 아키텍처 이미지 생성용 스크립트다.

## Rule Engine과 Fact Graph

Rule v2 계약은 `schemas/finops-rule-v2.schema.json`에 정의되어 있다.

```text
facts       판정에 사용하는 구조화 evidence
predicate   all / any / not과 비교 연산
thresholds  판정 경계값
outcome     severity, action, confidence
handlers    extractor, savings, remediation 구현 이름
```

Rule 파일은 시작 시 로드되며 알 수 없는 fact, operator, threshold, handler를 거부한다. 현재 rule catalog 기준으로 91개 `severity_rule`이 있다.

```text
finding  73
blocker   7
review   11
```

전체 분류표는 `RULE_CATALOG.md`에 있다.

Graph state의 finding에는 stable `run_id`, `finding_id`, `fact_id`, analyzer version, rule version, Terraform reference dependency, cross-domain reference가 포함된다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

테스트는 다음 영역을 확인한다.

- 18개 도메인 registry coverage
- Season 1/2 fixture 분석
- 복잡 도메인 Skill output 로딩과 request-only 경계
- 단순 및 GenAI Skill의 review-only 경계
- Rule v2 predicate와 handler 검증
- GenAI analyzer finding과 절감액
- Send fan-out, fallback enrichment, checkpoint interrupt/resume
- anomaly workflow와 cross-service dependency fact
- MiniStack 수집기의 읽기 전용 evidence 변환
- shared pricing cache와 pricing request 흐름
- token/cost usage snapshot
- legacy finalize 검증

## 문서

- `ARCHITECTURE.md`: LangGraph runtime, checkpoint, MCP adapter, approval flow
- `RULE_CATALOG.md`: Rule v2 severity_rule 전체 분류표
- `0622.md`: 구현 과정과 하이브리드 구조 설명
- `FINAL_REPORT.md`: 프로젝트 결과 정리

## License

MIT License

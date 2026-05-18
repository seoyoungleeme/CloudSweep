# MA-001 · Lambda + S3 + DynamoDB 결합 — 컨텍스트 분할 문제

> **회사**: PixelStorm · **인수자**: @seoyoungleeme
> Week 2 · 데드라인: 2026-05-18 (월요일 22:00 세션 전까지)

## 상황

B2C 앱의 주문 처리 인프라를 인수했습니다. Lambda 함수 다수가 메모리 과잉으로 할당되어 있고, S3 버킷에는 lifecycle 정책이 빠져 있고, DynamoDB 테이블은 피크 기준 프로비전드로 설정되어 평균 사용률이 10% 수준입니다. 3개 도메인이 동시에 무너진 상태인데, 단일 에이전트로 분석하면 컨텍스트 한계에 부딪힙니다.

이번 주차는 **단일 에이전트로는 풀기 어려운 결합 시나리오**를 받았습니다. 분석할 대상이 `main.tf` 한 파일에 모두 들어 있는데, 라인 수가 약 **208줄**이고 여러 도메인이 섞여 있습니다.

## 인프라에 심어진 문제 패턴

이 시나리오는 시즌 1에서 다뤘던 다음 단일 패턴들을 **한 인프라에 동시 발생**시킨 것입니다:

- `L2-014`
- `L1-011`
- `L1-010`

> 단일 패턴은 시즌 1 [scenarios-guide.md](https://github.com/cloud-club/09th-ai-cloud-finops/blob/main/platform/docs/scenarios-guide.md) 에서 정의를 확인할 수 있습니다.

## 데이터 자료

| 파일 | 내용 |
|------|------|
| `main.tf` | 결합된 Terraform (약 208줄, 컴포넌트별 prefix `comp1_` ~ `comp3_`) |
| `cost_report.json` | 6개월 비용 히스토리 + 서비스별 breakdown · 월 낭비 추정 약 **$1,436** |
| `metrics/metrics.json` | 30일 시간별 CloudWatch 메트릭 (모든 컴포넌트 리소스) |
| `hint.txt` | 멀티 에이전트 활용 힌트 |

## 분석 과제

1. **베이스라인 측정** — 본인의 현재 FinOps 도구(단일 에이전트 구조)로 이 시나리오를 분석. 발견 issue 수 / 토큰 사용량 / wall-clock 기록.
2. **멀티 에이전트 적용** — 본인 도구를 multi-agent로 리팩토링(or PoC) 후 같은 분석 재실행. 동일 metric 기록.
3. **결과 분석** — recall 향상 / 토큰 비용 변화 / emergent finding 도출 여부.

## 제출 형식

`Submit Answer` 페이지에서 시나리오 ID `MA-001`로 다음을 제출:
- **Analysis** — 발견한 문제, root cause, 권장 해결 (시즌 1 양식)
- **Optimized Terraform** — 결합 시나리오에서 수정한 `main.tf`
- **Estimated Monthly Savings** — 총 절감 추정액 (USD)
- **Report Upload** — `report.md` (단일 vs 멀티 비교 + 측정 데이터 + 회고)

## 힌트

Lambda 전문가 + Storage 전문가 + DynamoDB 전문가 + Orchestrator로 분할하면 cross-domain query가 가능해집니다.

평가 기준:
- 발견한 문제 정확성 + 누락 패턴 수
- root cause 분석 깊이
- 권장 해결의 실행 가능성
- (보너스) 단일 vs 멀티 에이전트 측정 데이터 정직성

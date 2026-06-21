# LV-001: 어제부터 발생한 비용 spike — 실시간 Cost Explorer 분석

## Scenario

프로덕션 환경에서 어제(약 25시간 전)부터 비정상적인 비용 증가가 감지되었습니다.
Cost Explorer의 시간별 데이터를 분석하여 spike의 원인을 자동으로 파악하는 에이전트를 구축하세요.

## Live APIs

| API | Purpose |
|-----|---------|
| `ce:GetCostAndUsage` (HOURLY granularity) | 시간별 비용 데이터 조회 |
| `ce:GetAnomalies` | 비용 이상 탐지 결과 조회 |

## Task

다음 기능을 수행하는 에이전트를 구축하세요:

1. **Spike 감지**: 시간별 비용 데이터에서 비정상적인 증가를 자동으로 탐지
2. **드릴다운 분석**: Service, UsageType 별로 비용을 분해하여 원인 서비스 식별
3. **CloudTrail 상관 분석**: spike 발생 시점 전후의 CloudTrail 이벤트와 연계하여 root cause 파악
4. **보고서 생성**: 분석 결과를 구조화된 형태로 출력

## Deliverables

- `solution.py` 또는 `solution.ts` — 에이전트 코드

## Evaluation Criteria

- 시간별 데이터에서 spike 시점을 정확히 식별하는가
- 다차원 드릴다운 로직이 체계적인가
- CloudTrail 이벤트와의 상관관계를 올바르게 분석하는가
- 코드 구조 및 에러 핸들링

# CloudSweep Final Report

## 1. 프로젝트 개요

CloudSweep는 Claude Code 환경에서 동작하도록 설계된 AWS FinOps 분석 툴킷이다. 목표는 Terraform으로 정의된 AWS 인프라, CloudWatch 지표, 비용 리포트, 태그/비즈니스 메타데이터를 함께 읽고, 단순한 비용 절감 아이디어가 아니라 근거가 있는 최적화 결과물을 산출하는 것이다.

이 레포는 일반적인 스크립트형 CLI 도구라기보다, `.claude/skills` 아래에 Claude Code용 FinOps skill들을 구성한 분석 프레임워크에 가깝다. 사용자가 특정 샘플 또는 실제 워크로드 디렉터리에서 FinOps 분석을 요청하면, 최상위 `finops` orchestrator skill이 리소스 유형을 식별하고 서비스별 skill로 분석 방식을 라우팅한다.

핵심 산출물은 다음 두 가지다.

| 산출물 | 설명 |
|--------|------|
| `finops_report.md` | 발견된 비용 낭비, 증거, 원인, 조치안, 예상 절감액을 정리한 분석 보고서 |
| `main_optimized.tf` | Terraform 수준에서 적용 가능한 최적화 예시 |

분석 과정에서 필요한 경우 `parsed_input.json`, `findings.json`도 생성한다. 이 파일들은 원본 Terraform, 메트릭, 비용 데이터를 분석 가능한 중간 구조로 변환하고, rule 기반 탐지 결과를 저장하기 위한 보조 산출물이다.

## 2. 레포 구조

```text
CloudSweep/
  README.md
  pricing_test_result.json
  .claude/
    settings.local.json
    skills/
      finops/
      finops-rds/
      finops-elb/
      finops-ebs/
      finops-s3/
      finops-cloudwatch/
      finops-cloudwatch-alarm/
      finops-dynamodb/
      finops-lambda/
      finops-ecs/
      finops-elasticache/
      finops-sqs/
      finops-kinesis/
      finops-nat/
      finops-tgw/
      finops-organizations/
  sample/
    L1-004/
    L1-005/
    ...
    L3-034/
```

현재 README는 초기 범위인 RDS, ELB, EBS, S3 중심으로 설명되어 있지만, 실제 레포는 CloudWatch, DynamoDB, Lambda, ECS/Fargate, ElastiCache, SQS, Kinesis, NAT Gateway, Transit Gateway, AWS Organizations까지 확장되어 있다.

## 3. 분석 입력 데이터

CloudSweep는 한 파일만 보고 판단하지 않고, 가능한 한 여러 증거를 교차 검증한다.

| 파일 | 역할 |
|------|------|
| `main.tf` | Terraform 리소스 정의. 어떤 AWS 리소스가 있고 어떤 설정이 비용 낭비를 만들 수 있는지 확인한다. |
| `metrics.json` 또는 `metrics/metrics.json` | 30일 CloudWatch 지표 또는 시나리오 지표. 평균뿐 아니라 p95, p99, peak, idle 여부를 판단한다. |
| `cost_report.json` | 6개월 비용 추이, 서비스별 비용, pricing note, 권위 있는 시나리오 절감액 근거를 제공한다. |
| `business_metrics.json` | 비즈니스 트래픽, 업무 중요도, 사용 패턴 등 기술 지표만으로 판단하기 어려운 맥락을 보완한다. |
| `tags_inventory.json` | Owner, Team, CostCenter, Env 등 태그 거버넌스 상태를 확인한다. |
| `ri_sp_coverage.json` | RI/Savings Plans 커버리지, 온디맨드 비중, commitment 최적화 가능성을 판단한다. |
| `cur_report.csv` | L3 문제에서 CUR 유사 데이터로 비용 항목을 더 세밀하게 검증한다. |
| `findings.json` | analyzer가 탐지한 rule firing 결과. |
| `parsed_input.json` | parser가 만든 정규화된 입력 데이터. |

중요한 원칙은 "제공된 데이터에 없는 사실은 추측하지 않는다"는 것이다. skill 문서 전반에 `Not available in the provided data; verify in the real environment.`라는 문구가 반복되는 이유도 여기에 있다.

## 4. FinOps 구현 로직

CloudSweep의 전체 분석 흐름은 다음과 같다.

1. 워크스페이스에서 `main.tf`, `metrics.json`, `cost_report.json` 등 입력 파일을 찾는다.
2. `finops` orchestrator가 Terraform 리소스와 비용 증거를 보고 어떤 서비스 skill을 적용할지 결정한다.
3. 서비스별 skill이 자체 rule JSON과 safety check를 적용한다.
4. 단순 평균이 아니라 p95, peak, throttling, 오류, 라우팅, 태그, RI/SP, 비용 항목 등을 교차 확인한다.
5. 최적화가 안전하면 `main_optimized.tf`를 생성한다.
6. `finops_report.md`에 문제, 증거, 원인, 조치, 예방책, 절감액 산식을 기록한다.

이 구조는 "비용이 높다"에서 바로 "삭제하자"로 가지 않도록 설계되어 있다. 예를 들어 NAT Gateway 비용이 높아도 인터넷 egress가 남아 있으면 NAT 자체를 삭제하지 않고, S3/DynamoDB endpoint로 우회 가능한 트래픽만 분리한다. RDS가 낮은 CPU를 보이더라도 memory, IOPS, latency, connection, Multi-AZ, RI coverage를 확인하기 전에는 downsizing을 확정하지 않는다.

## 5. Orchestrator Skill

`finops` skill은 전체 라우터 역할을 한다.

| 감지 리소스 또는 증거 | 연결 skill |
|----------------------|------------|
| `aws_lb`, ALB, ELB | `finops-elb` |
| `aws_ebs_snapshot` | `finops-ebs` |
| `aws_db_instance`, RDS | `finops-rds` |
| `aws_s3_bucket`, versioning/lifecycle | `finops-s3` |
| `aws_cloudwatch_log_group` | `finops-cloudwatch` |
| `aws_cloudwatch_metric_alarm` | `finops-cloudwatch-alarm` |
| `aws_dynamodb_table` | `finops-dynamodb` |
| `aws_lambda_function` | `finops-lambda` |
| `aws_ecs_service`, `aws_ecs_task_definition` | `finops-ecs` |
| `aws_elasticache_replication_group` | `finops-elasticache` |
| `aws_sqs_queue` | `finops-sqs` |
| `aws_kinesis_stream` | `finops-kinesis` |
| `aws_nat_gateway`, VPC endpoint | `finops-nat` |
| `aws_ec2_transit_gateway`, TGW attachment, VPC peering | `finops-tgw` |
| AWS Organizations, RI/SP pooling | `finops-organizations` |

Orchestrator의 guardrail은 크게 다섯 가지다.

| Guardrail | 의미 |
|-----------|------|
| Scenario match | Terraform의 실제 리소스와 선택된 skill이 일치해야 한다. |
| Cross evidence | Terraform, metrics, cost 증거를 함께 본다. |
| Decoy preservation | 정상 리소스나 decoy 리소스는 변경하지 않는다. |
| Savings accuracy | 영향 받은 리소스에 대해서만 절감액을 계산한다. |
| Report completeness | 문제, 증거, 원인, 조치, 예방, 절감액을 빠뜨리지 않는다. |

## 6. 서비스별 Skill과 탐지 로직

### 6.1 RDS

`finops-rds`는 RDS 인스턴스 overprovisioning, 불필요한 Multi-AZ, storage/IOPS 과다 설정, Extended Support 비용, Reserved DB Instance 커버리지 부족을 탐지한다.

핵심 rule은 다음과 같다.

| Rule | 판단 기준 | 조치 |
|------|-----------|------|
| R1 | non-prod에서 Multi-AZ가 켜져 있고 SLA/DR 근거가 없음 | Single-AZ 검토 |
| R2 | CPU, memory, connection, I/O가 모두 낮고 p95/peak 안전 | 인스턴스 downsizing 검토 |
| R3 | storage, IOPS, throughput이 관측 사용량보다 큼 | storage/IOPS 조정 검토 |
| R4 | 표준 지원 종료 엔진으로 Extended Support 비용 발생 | 엔진 업그레이드 |
| R5 | 안정적 baseline이 있는데 RI 커버리지 없음 | Reserved DB Instance 모델링 |
| R6 | 성능 위험 지표 존재 | downsizing 금지, 성능 검토 |

튜닝 포인트는 평균 CPU만으로 downsizing하지 않도록 한 것이다. p95/max CPU, FreeableMemory, SwapUsage, latency, DiskQueueDepth, IOPS, connection을 함께 확인하도록 보완했다.

### 6.2 ELB

`finops-elb`는 사용되지 않는 ALB/ELB를 탐지한다. Terraform의 `aws_lb`, listener, target group, metrics의 request count, healthy host, cost report의 ELB 비용을 함께 본다.

주요 판단은 다음과 같다.

| 판단 | 설명 |
|------|------|
| 요청이 거의 없음 | request count 또는 processed bytes가 장기간 낮음 |
| 타깃이 없음 | target group이 비어 있거나 healthy host가 없음 |
| DNS/서비스 연결 근거 없음 | 실제 진입점으로 쓰인다는 근거가 부족 |
| 비용 발생 | hourly 또는 LCU 비용이 계속 발생 |

ELB는 삭제가 실제 트래픽 단절로 이어질 수 있기 때문에, 분석 보고서에는 DNS, listener, target group, access log 확인을 포함하도록 튜닝했다.

### 6.3 EBS

`finops-ebs`는 orphaned snapshot을 중심으로 탐지한다. snapshot이 어떤 volume/instance와 연결되는지, 오래된 백업인지, 보존 정책이 있는지, 비용이 어느 정도인지 확인한다.

튜닝 포인트는 "오래된 snapshot은 삭제"가 아니라 "보존 의무와 복구 필요성이 없는 orphaned snapshot만 삭제 후보"로 좁힌 것이다. backup, compliance, retention tag가 있으면 삭제 대신 review로 남기도록 했다.

### 6.4 S3

`finops-s3`는 versioning이 켜진 버킷에서 noncurrent version이 누적되는데 lifecycle policy가 없는 경우를 주로 탐지한다.

| Rule | 판단 기준 | 조치 |
|------|-----------|------|
| V1 | versioning enabled, noncurrent version 증가, noncurrent expiration 없음 | 안전한 lifecycle 추가 |
| V2 | incomplete multipart upload 누적 | abort incomplete multipart upload rule 추가 |
| V3 | Object Lock, legal hold, compliance, replication 존재 | 만료 금지, 정책 검토 |
| V4 | 낮은 접근 빈도의 오래된 객체 | storage class transition 모델링 |
| V5 | lifecycle 관련 태그 부족 | governance tag 추가 |

튜닝 포인트는 S3 lifecycle의 위험성을 반영한 것이다. `NoncurrentVersionExpiration`은 데이터를 영구 삭제할 수 있으므로, restore window, Object Lock, replication, backup, legal hold가 확인되지 않으면 공격적인 삭제 정책을 피하도록 설계했다.

### 6.5 CloudWatch Logs

`finops-cloudwatch`는 log group의 `retention_in_days` 누락, 0 또는 무한 보존, 환경 대비 과도한 retention을 탐지한다.

환경별 기본값은 dev/test 14-30일, staging 30-90일, prod application 90-365일, unknown 90일이다. audit/security/compliance 로그는 비용만 보고 줄이지 않고 조직 정책을 따르도록 했다.

튜닝 포인트는 Terraform AWS provider의 실제 속성인 `retention_in_days`와 시나리오용 속성인 `retention_days`를 구분한 것이다. optimized Terraform에서는 provider-valid attribute로 정규화한다.

### 6.6 CloudWatch Metric Alarm

`finops-cloudwatch-alarm`은 1초 high-resolution custom metric alarm이 실제로는 60초 standard resolution으로 충분한 경우를 탐지한다.

| Rule | 판단 기준 | 조치 |
|------|-----------|------|
| M1 | `resolution_seconds = 1`, 실제 필요 해상도는 60초 이상 | standard로 downgrade |
| M2 | high-resolution인데 evaluation window가 1분 이상 | standard로 downgrade |
| M3 | high-resolution alarm이 대량 존재하고 SLA 근거 없음 | review |
| M4 | scenario-only Terraform attribute 존재 | provider attribute로 정규화 |

비용 모델은 high-resolution custom metric 월 $0.90, standard 월 $0.30, 절감액 월 $0.60 per metric을 fallback으로 사용한다. cost report에 pricing note가 있으면 그것을 우선한다.

### 6.7 DynamoDB

`finops-dynamodb`는 provisioned RCU/WCU 과다 설정, GSI 과다 설정, Auto Scaling 부재, 부적절한 billing mode를 탐지한다.

튜닝 포인트는 DynamoDB에서 평균 사용률만 보지 않도록 한 것이다. p95, peak, throttled request, hot partition 위험, GSI별 독립 capacity, reserved capacity까지 고려한다. throttling이 있으면 절감보다 안정성 문제로 분류한다.

### 6.8 Lambda

`finops-lambda`는 memory over-allocation, timeout 과다, provisioned concurrency 낭비, ephemeral storage 과다, architecture 전환 가능성, error/retry 비용을 탐지한다.

핵심 원칙은 Lambda memory가 CPU/network 성능과 연결된다는 점이다. 따라서 max memory used만 낮다고 바로 memory를 줄이지 않고, p95/p99 duration, error, timeout, throttle, cold start, power tuning 필요성을 함께 본다.

L2 샘플에서는 Lambda overprovisioning과 timeout waste를 다루며, 단순 memory 축소뿐 아니라 timeout 값이 p99 duration 대비 과하게 큰지도 분석한다.

### 6.9 ECS/Fargate

`finops-ecs`는 Fargate task CPU/memory overprovisioning, static desired count, Auto Scaling 부재, platform version 고정을 탐지한다.

right-sizing은 다음 방식으로 계산한다.

```text
target_cpu = p95_actual_cpu * 1.3
target_memory = p95_actual_memory * 1.3
```

이후 Fargate가 지원하는 CPU/memory 조합으로 올림 처리한다. CPU max가 80% 이상이거나 memory max가 90% 이상이면 축소하지 않는다.

### 6.10 ElastiCache

`finops-elasticache`는 Redis/ElastiCache replication group의 노드 타입, shard/replica 수, CPU, memory, evictions, connections, network throughput, reserved node 커버리지를 함께 본다.

튜닝 포인트는 cache workload의 위험을 반영한 것이다. 평균 CPU가 낮아도 memory pressure, eviction, connection spike, failover/HA 요구가 있으면 downsize하지 않는다.

### 6.11 SQS

`finops-sqs`는 short polling으로 인한 empty receive 비용, batching 부족, retry/visibility timeout 문제, DLQ 이동을 탐지한다.

| Rule | 판단 기준 | 조치 |
|------|-----------|------|
| Q1 | `receive_wait_time_seconds = 0`, empty receive가 많음 | long polling 활성화 |
| Q2 | long polling 중인데 empty receive가 높음 | consumer polling 검토 |
| Q3 | request volume이 큰데 batch API 사용 낮음 | batching 검토 |
| Q4 | retry, DLQ, message age가 비용 증가 유발 | visibility/retry 개선 |
| Q5 | client timeout 불명확 | timeout 검증 |

튜닝 포인트는 모든 queue에 무조건 20초 long polling을 넣지 않는 것이다. consumer read timeout, latency SLA, Lambda event source behavior, FIFO throughput을 확인하도록 했다.

### 6.12 Kinesis

`finops-kinesis`는 Enhanced Fan-Out(EFO) 소비자가 실제 트래픽 대비 과한 비용을 만들거나, shard/consumer 모델이 맞지 않는 경우를 탐지한다.

EFO는 저지연 fan-out이 필요한 소비자에게는 유용하지만, 단순 배치/저빈도 consumer에는 비용 낭비가 될 수 있다. 따라서 consumer lag, read throughput, consumer count, latency requirement를 함께 확인하도록 구성되어 있다.

### 6.13 NAT Gateway

`finops-nat`는 NAT Gateway hourly/data processing/cross-AZ 비용 중 endpoint로 우회 가능한 트래픽을 탐지한다.

| Rule | 판단 기준 | 조치 |
|------|-----------|------|
| N1 | same-region S3 트래픽이 NAT를 통과하고 올바른 S3 gateway endpoint 없음 | S3 gateway endpoint 추가 |
| N2 | DynamoDB 트래픽이 NAT를 통과하고 endpoint 없음 | DynamoDB gateway endpoint 추가 |
| N3 | AWS service 트래픽이 많고 interface endpoint가 더 저렴할 가능성 | interface endpoint 모델링 |
| N4 | 다른 AZ의 NAT를 사용 | AZ-local NAT/endpoint 검토 |
| N5 | offload 후 NAT hourly만 남음 | NAT 제거 검토 |
| N6 | endpoint는 있으나 region/route/DNS/policy/security group이 잘못됨 | endpoint 설정 수정 |

L3-029에서는 S3 Gateway Endpoint의 `service_name`이 `com.amazonaws.ap-northeast-2.s3`로 되어 있어, `us-east-1` 워크로드의 S3 트래픽이 NAT를 통해 나가는 문제가 탐지되었다. optimized Terraform은 이를 `com.amazonaws.us-east-1.s3`로 수정한다.

### 6.14 Transit Gateway

`finops-tgw`는 Transit Gateway data processing charge와 attachment cost가 VPC Peering으로 대체 가능한지 분석한다.

| Rule | 판단 기준 | 조치 |
|------|-----------|------|
| T1 | same-region VPC-to-VPC 트래픽이 TGW data processing 비용을 만들고 peering으로 대체 가능 | VPC Peering migration |
| T2 | 2-3개 attachment의 단순 point-to-point topology | peering 전환 검토 |
| T3 | traffic이 거의 없는 attachment가 hourly cost 발생 | idle attachment 검토 |
| T4 | cross-AZ TGW routing overhead 존재 | AZ-local routing 검토 |

튜닝 포인트는 TGW를 단순히 비싸다고 제거하지 않는 것이다. TGW는 hub-spoke, transitive routing, centralized inspection, Direct Connect/VPN, multi-account routing에 필요할 수 있으므로, 이런 요구가 없는 단순 topology일 때만 peering을 권고한다.

### 6.15 AWS Organizations

`finops-organizations`는 consolidated billing, RI/SP sharing, account enrollment, volume discount, commitment coverage를 분석한다.

L3-034에서는 조직은 존재하고 consolidated billing 모델도 가능하지만, 10개 account가 enrollment/share 범위 밖에 있어 RI/SP pooling과 volume discount를 놓치는 문제가 탐지되었다. cost report의 authoritative pricing note에 따라 월 약 $3,000, 연 약 $36,000 절감 가능성이 보고되었다.

튜닝 포인트는 "새 RI/SP 구매"와 "기존 commitment 공유/조직 통합"을 분리한 것이다. 즉시 절감 가능한 consolidated billing savings와, 추가 구매가 필요한 modeled commitment savings를 구분해 과대 산정을 피한다.

## 7. Rule 파일 기반 튜닝

각 skill은 `rules/*.json`에 탐지 조건, threshold, cost fallback, safety check, policy control을 담고 있다. 이 구조 덕분에 skill 본문은 분석 절차를 설명하고, rule JSON은 조정 가능한 정책 레이어 역할을 한다.

대표적인 튜닝 방향은 다음과 같다.

| 영역 | 튜닝 내용 |
------|-----------|
| 평균 중심 판단 제거 | 대부분의 right-sizing rule에서 avg뿐 아니라 p95, max, throttling, latency, memory, I/O를 확인하도록 보완했다. |
| decoy 보존 | 정상 리소스, active 리소스, compliant 리소스를 optimized Terraform에서 건드리지 않도록 orchestrator guardrail을 추가했다. |
| 삭제보다 설정 개선 우선 | lifecycle, retention, polling, endpoint, rightsizing 문제는 삭제보다 설정 변경을 우선한다. |
| compliance 보호 | S3 Object Lock, CloudWatch audit/security log, EBS retention, RDS DR/SLA 등 보존/가용성 요구가 있으면 절감 조치를 review로 낮춘다. |
| 비용 산정 우선순위 | cost report 또는 pricing note를 최우선으로 쓰고, 없으면 AWS Pricing API/MCP, 마지막으로 rule의 static fallback을 사용한다. |
| provider-valid Terraform | 시나리오용 속성은 evidence로만 보고, optimized Terraform은 실제 AWS provider attribute로 정규화한다. |
| L3 복합성 반영 | CUR, RI/SP, tags, business metrics를 함께 사용해 네트워크와 조직/할인 구조 문제까지 분석한다. |

## 8. Pipeline Script

일부 초기 skill은 Python pipeline을 포함한다.

| Skill | Script | 역할 |
|-------|--------|------|
| `finops-elb` | `parser.py`, `analyzer.py`, `formatter.py` | Terraform/metrics/cost를 파싱하고 unused ELB finding 및 report 생성 |
| `finops-ebs` | `parser.py`, `analyzer.py`, `formatter.py` | snapshot/volume 관계와 비용 근거를 정규화하고 orphaned snapshot 보고 |
| `finops-rds` | `parser.py`, `analyzer.py`, `formatter.py` | RDS 설정, 지표, 비용을 rule 기반으로 분석 |
| `finops-s3` | `parser.py`, `analyzer.py`, `formatter.py` | S3 lifecycle/versioning 문제를 분석하고 보고서 생성 |

후속 skill들은 script보다 skill 문서와 rule JSON 중심으로 확장되어 있다. 이는 문제 유형이 다양해지면서 정형 parser만으로 처리하기 어려운 복합 증거, 예를 들어 NAT route table, Organizations RI/SP coverage, TGW topology를 다루기 위해서다.

## 9. MCP 및 외부 데이터 연결

이 레포에서 확인되는 MCP/외부 연결의 역할은 다음과 같다.

| 연결 | 역할 |
|------|------|
| GitHub API / WebFetch | 외부 문제 샘플의 README, Terraform, metrics, cost report를 가져오는 데 사용된 흔적이 있다. `.claude/settings.local.json`에 `gh api`, `raw.githubusercontent.com`, `api.github.com` 접근 허용 내역이 있다. |
| AWS Pricing API | `pricing_test_result.json`에 AWS Pricing API global endpoint를 통해 EC2, EBS gp3, ALB hourly 가격을 조회한 결과가 저장되어 있다. |
| AWS Documentation MCP | `.claude/settings.local.json`에 `awslabs.aws-documentation-mcp-server` 실행 및 모듈 확인 흔적이 있다. AWS 서비스 동작과 공식 문서 근거를 확인하기 위한 연결로 볼 수 있다. |
| AWS CLI | `aws configure`, `aws sts` 관련 허용 내역이 있어 실제 AWS 계정/가격/상태 검증으로 확장할 수 있는 준비가 되어 있다. |

현재 레포 루트에는 별도의 MCP 설정 파일이 보이지 않는다. 따라서 이 보고서에서는 "연결된 MCP"를 레포 내부에 고정된 설정이라기보다, CloudSweep 개발/검증 과정에서 사용되거나 사용 가능하도록 준비된 외부 근거 채널로 해석한다.

MCP/외부 데이터는 세 가지 역할을 한다.

1. 공식 가격 검증: static fallback 대신 region-specific pricing을 확인한다.
2. 공식 문서 검증: Terraform 속성, AWS 서비스 제약, endpoint/TGW/RI/SP 동작을 확인한다.
3. 샘플 수집: 외부 GitHub 문제 세트를 로컬 `sample/`로 가져와 skill을 테스트한다.

## 10. 샘플 시나리오 커버리지

현재 `sample/` 디렉터리는 L1, L2, L3 난이도로 구성되어 있다.

| Scenario | 주요 서비스 | 주제 |
|----------|-------------|------|
| L1-004 | RDS | overprovisioning |
| L1-005 | ALB/ELB | unused load balancer |
| L1-006 | CloudWatch Logs | retention 또는 unused log cost |
| L1-007 | EBS | orphaned snapshot / unused storage |
| L1-010 | DynamoDB | provisioned capacity overprovisioning |
| L1-012 | S3 | versioning/lifecycle waste |
| L2-014 | Lambda | memory overprovisioning |
| L2-015 | Lambda | timeout waste |
| L2-016 | ECS/Fargate | task CPU/memory overprovisioning |
| L2-019 | ElastiCache | node/replica overprovisioning |
| L2-021 | SQS | short polling/API call waste |
| L2-022 | Kinesis | pricing model/EFO waste |
| L2-024 | CloudWatch Alarm | high-resolution metric overprovisioning |
| L3-026 | VPC/TGW | network architecture cost |
| L3-029 | VPC/S3/NAT Gateway | S3 NAT bypass and endpoint misconfiguration |
| L3-034 | AWS Organizations | consolidated billing and RI/SP sharing |

L1은 단일 리소스의 명확한 낭비를 찾는 문제에 가깝고, L2는 서비스별 운영 지표와 비용 산식이 더 중요하다. L3는 단일 리소스 조정이 아니라 네트워크 topology, 조직 계정 구조, CUR, RI/SP, 태그 거버넌스까지 함께 고려해야 한다.

## 11. 산출 보고서 형식

샘플의 `finops_report.md`들은 대체로 다음 구조를 따른다.

1. Problem Identification
2. Evidence
3. Infrastructure Evidence
4. Metrics Evidence
5. Cost Evidence
6. Root Cause
7. Proposed Solution
8. Preventive Actions
9. Estimated Monthly Savings
10. Optimized Terraform

이 형식은 평가자가 "무엇을 고쳤는지"뿐 아니라 "왜 그 조치가 안전한지"와 "절감액이 어떻게 계산됐는지"를 확인할 수 있게 한다.

## 12. 대표 결과 요약

### L3-029 NAT Gateway

문제는 `us-east-1` 환경에 `ap-northeast-2` S3 Gateway Endpoint service name이 들어간 것이었다. endpoint 리소스는 존재했지만 region이 맞지 않아 S3 트래픽이 endpoint route와 매칭되지 않고 NAT Gateway를 통과했다.

결과:

| 항목 | 내용 |
|------|------|
| 주요 finding | wrong-region S3 Gateway Endpoint |
| 조치 | `service_name`을 `com.amazonaws.us-east-1.s3`로 수정 |
| 보수적 절감액 | 월 약 $119 |
| 최대 시나리오 절감액 | 월 약 $360 |
| Terraform 변경 | endpoint service name 단일 변경 |

### L3-034 AWS Organizations

문제는 10개 계정이 consolidated billing/RI-SP sharing 범위 밖에 있어 commitment와 volume discount를 공유하지 못하는 것이었다.

결과:

| 항목 | 내용 |
|------|------|
| 주요 finding | all accounts not enrolled in consolidated billing |
| 조치 | account enrollment, RI/SP sharing 활성화, chargeback/tag governance 검증 |
| authoritative 절감액 | 월 약 $3,000 |
| 연간 절감액 | 약 $36,000 |
| 주의점 | 신규 commitment 구매 절감액은 별도로 모델링하며 즉시 절감액에 합산하지 않음 |

## 13. 보완해야 할 점

CloudSweep는 샘플 문제를 해결하는 수준을 넘어 실제 FinOps 분석기로 확장할 수 있는 구조를 갖췄지만, 더 강화할 부분도 있다.

| 영역 | 보완안 |
|------|--------|
| README 갱신 | 현재 README가 초기 4개 skill만 설명하므로 전체 skill 목록과 L1/L2/L3 사용법을 반영해야 한다. |
| MCP 설정 명문화 | AWS Docs MCP, AWS Pricing API, GitHub 연동 방법을 문서화하면 재현성이 좋아진다. |
| 공통 report template | 모든 skill의 보고서 헤더, evidence, savings 형식을 통일하면 평가와 비교가 쉬워진다. |
| 공통 parser 인터페이스 | script가 있는 skill과 문서/rule만 있는 skill 사이의 실행 방식이 다르므로, 공통 runner를 만들 수 있다. |
| 가격 검증 자동화 | rule JSON의 static fallback을 AWS Pricing API 결과로 자동 대체하면 region-specific 정확도가 높아진다. |
| Terraform validation | `terraform fmt`, `terraform validate`, provider schema check를 산출 단계에 추가하면 optimized Terraform 품질이 높아진다. |
| 인코딩 정리 | 일부 샘플 README가 깨져 있어 UTF-8 기준으로 정리하면 보고서 품질이 좋아진다. |
| 테스트 추가 | 각 skill별 fixture와 expected findings를 두고 regression test를 만들면 rule 튜닝 후 품질을 보장할 수 있다. |

## 14. 결론

CloudSweep는 AWS 비용 최적화를 "아이디어 제안"이 아니라 "증거 기반 분석과 Terraform remediation"으로 연결하는 Claude Code-native FinOps toolkit이다. 단일 서비스의 낭비 탐지부터 L3 수준의 네트워크/조직/할인 구조 분석까지 다루며, skill과 rule JSON을 분리해 확장성과 튜닝 가능성을 확보했다.

가장 중요한 설계 철학은 안전한 절감이다. 비용 절감 가능성이 있어도 성능, 가용성, 규정 준수, 라우팅, 계정 거버넌스 증거가 부족하면 즉시 변경하지 않고 검토 항목으로 남긴다. 이 접근 덕분에 CloudSweep는 샘플 문제 풀이뿐 아니라 실제 AWS FinOps 검토 프로세스의 초안으로도 사용할 수 있다.

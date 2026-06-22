# Rule Catalog — CloudSweep 전체 규칙 분류표

**기준:** Rule JSON (`severity_rules`) 이 canonical source.  
SKILL.md 기술과 JSON 간 충돌이 있으면 JSON 우선.  
현재 Python 구현 상태는 `graph.py` 기준.

## 요약

| 유형 | 수 | 설명 |
|------|:--:|------|
| **finding** | 73 | 비용 절감 기회를 생성하는 규칙 |
| **blocker** | 7 | downsizing·삭제를 막는 안전 규칙 |
| **review** | 11 | SLA·DR·소유권·compliance Claude 판단 필요 |
| **합계** | **91** | |

구현 상태:
- `ok` — 올바른 rule_id, 올바른 조건, JSON threshold와 일치
- `wrong-id` — 규칙이 있으나 rule_id 또는 의미가 JSON과 다름
- `stub` — 조건 일부만 구현 (threshold 누락 등)
- `missing` — graph.py에 없음

---

## Lambda (L1–L7)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| L1 | finding | RIGHTSIZE_MEMORY | avg(max_mem/mem_size)<0.5, max<0.75, errors==0, throttles==0 | stub | p95/max duration 모델 미확인 |
| L2 | finding | REDUCE_TIMEOUT | timeout≥300s, duration_p99 < timeout/3 | stub | upstream contract 체크 없음 |
| L3 | finding | TUNE_PROVISIONED_CONCURRENCY | provisioned_concurrency_enabled, util_avg<0.3 | stub | schedule 체크 없음 |
| L4 | finding | REVIEW_EPHEMERAL_STORAGE | ephemeral_storage_mb>512, usage unknown | stub | |
| L5 | finding | MODEL_ARM64 | architecture==x86_64, arm64 cost lower | stub | cost model 미구현 |
| L6 | finding | FIX_ERROR_RETRY_COST | errors>0 OR timeouts>0 OR retries_high | stub | |
| L7 | finding | REDUCE_DEPENDENCY_CALLS_OR_CACHE | downstream_requests_high, cache_hit_rate low | missing | |

---

## S3 (V1–V5, R1)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| V1 | finding | ADD_SAFE_LIFECYCLE_POLICY | versioning_enabled, noncurrent_slope>0.1, no retention blocker | stub | |
| V2 | finding | ADD_MULTIPART_ABORT | incomplete_mpu_age≥7d, no abort rule | stub | |
| V3 | **blocker** | DO_NOT_EXPIRE_WITHOUT_POLICY_REVIEW | object_lock OR legal_hold OR replication | missing | 현재 구현 없음 — lifecycle 적용 시 체크해야 함 |
| V4 | finding | MODEL_STORAGE_CLASS_TRANSITION | old objects + low access + no lifecycle transition | missing | |
| V5 | review | ADD_GOVERNANCE_TAGS | missing Owner/DataClass/RetentionDays/CostCenter | missing | |
| R1 | finding | REDUCE_REQUESTS_OR_ADD_CACHE | GET/HEAD rate high, cache_hit_rate low | missing | |

---

## DynamoDB (D1–D8)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| D1 | finding | REDUCE_WCU / ADD_WRITE_AUTOSCALING | billing_mode=PROVISIONED, avg(wcu)<0.20, p95<0.50, throttles==0 | stub | |
| D2 | finding | REDUCE_RCU / ADD_READ_AUTOSCALING | billing_mode=PROVISIONED, avg(rcu)<0.20, p95<0.50, throttles==0 | stub | |
| D3 | finding | ADD_AUTOSCALING | billing_mode=PROVISIONED, no autoscaling target/policy | stub | |
| D4 | finding | CONSIDER_PROVISIONED | billing_mode=PAY_PER_REQUEST, steady traffic, provisioned cheaper | missing | |
| D5 | finding | RIGHTSIZE_GSI / ADD_GSI_AUTOSCALING | gsi_provisioned, avg(gsi_util)<0.20, p95<0.50, throttles==0 | missing | |
| D6 | review | ANALYZE_NON_CAPACITY_COST | cost_report shows storage/backup/PITR dominates | missing | |
| D7 | **blocker** | DO_NOT_REDUCE_CAPACITY_REVIEW_THROTTLING | throttled_reads>0 OR throttled_writes>0 | missing | 현재 구현 없음 |
| D8 | review | CHECK_RESERVED_CAPACITY_COVERAGE | reserved_capacity_commitments present | missing | |

---

## Bedrock (B1–B4)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| B1 | finding | MODEL_THROUGHPUT_COMMIT | on_demand>committed, savings≥10%, util≥60%, cv≤0.35 | stub | |
| B2 | finding | REVIEW_COMMITTED_THROUGHPUT | committed_exists, effective_util<40% | stub | |
| B3 | finding | ENABLE_PROMPT_CACHING | repeated_prefix≥1024 tokens, requests≥100/day, cache_read==0 | stub | |
| B4 | finding | ADD_SEMANTIC_CACHE | similar_query_rate≥15%, expected_hit≥30%, no semantic cache | stub | |

---

## SageMaker (SM1–SM4)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| SM1 | finding | ADD_TARGET_TRACKING | initial_count>1, no appautoscaling | ok | |
| SM2 | finding | ADD_SCHEDULED_SCALING | predictable_low_traffic, no scheduled_action | stub | traffic pattern 판단 없음 |
| SM3 | finding | RIGHTSIZE_VARIANT | gpu_util_avg<25%, gpu_mem_p95<60%, p95_latency headroom, errors==0 | ok | |
| SM4 | finding | EVALUATE_ASYNC_SERVERLESS_BATCH | real_time, idle/bursty traffic, no strict latency SLA | stub | |

---

## EC2 (EC2G1–EC2G4)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| EC2G1 | finding | ADD_INSTANCE_SCHEDULER | accelerator_instance, off_hours≥40/wk, no schedule | ok | |
| EC2G2 | finding | ADD_SSM_OR_EVENTBRIDGE_SCHEDULE | accelerator, dev/training role, gpu_util<20%, no schedule | ok | |
| EC2G3 | finding | ADD_ASG_SCHEDULE_OR_SCALING | gpu ASG, desired_capacity static, no scheduled action | ok | |
| EC2G4 | review | INCLUDE_RESIDUAL_COSTS | stop schedule recommended, EBS/EIP costs unknown | stub | 절감 caveat, savings 과대계상 방지 |

---

## ECS (E1–E4) ⚠️ SKILL.md ↔ JSON 불일치

JSON 기준 (canonical):

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| E1 | finding | RIGHTSIZE_CPU | launch_type=FARGATE, cpu_avg<20%, cpu_p95<50%, cpu_max<80% | **wrong-id** | 구현 있음. 단 `ECS_E1_FARGATE_RIGHTSIZE`라는 다른 ID 사용 |
| E2 | finding | RIGHTSIZE_MEMORY | launch_type=FARGATE, mem_avg<20%, mem_p95<50%, mem_max<90% | **wrong-id** | 현재 구현 E2는 EC2 launch type (의미 다름) |
| E3 | finding | ADD_ECS_AUTOSCALING | desired_count static, no appautoscaling_target | **wrong-id** | 구현 있음, ID 다름 |
| E4 | finding | UPDATE_PLATFORM_VERSION | platform_version != LATEST (pinned e.g. 1.3.0) | missing | 현재 미구현 |

SKILL.md에서 파생된 규칙 (JSON에 없음, 제거 또는 ID 재정의 필요):
- `ECS_E2_EC2_UNDERUTILIZED` → JSON E2와 충돌, 별도 rule ID 필요
- `ECS_E3_MISSING_AUTOSCALING` → E3 re-ID

---

## ElastiCache (EC1–EC5) ⚠️ SKILL.md ↔ JSON 불일치

JSON 기준 (canonical):

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| EC1 | finding | REDUCE_REPLICAS | replicas>1, hit_rate≥99%, mem_p95≤50%, evictions==0, cpu_p95≤50%, lag_p95≤1s | **wrong-id** | 구현 있음. 단 evictions·lag 조건이 권고문에만 있고 실제 평가 안 됨 |
| EC2 | finding | DOWNSIZE_NODE_TYPE | mem_p95≤50%, cpu_p95≤50%, network_p95≤50%, evictions==0 | **wrong-id** | 구현 있음. network_p95 조건 누락 |
| EC3 | finding | REVIEW_SHARD_COUNT | cluster_mode_enabled, per_shard_mem_p95 low, per_shard_cpu_p95 low, traffic steady | **wrong-id** | 현재 구현 EC3는 RI coverage (의미 완전히 다름) |
| EC4 | finding | CONSIDER_RESERVED_NODES | steady baseline, reserved_node_coverage_missing | **wrong-id** | 현재 구현 EC4는 HA posture (의미 다름) |
| EC5 | **blocker** | DO_NOT_DOWNSIZE_REVIEW_PERFORMANCE | evictions>0 OR mem_p95>50% OR cpu_p95>50% OR lag_p95>1s | **wrong-id** | 현재 구현 EC5는 engine EOL finding (완전히 반대 의미) |

SKILL.md에서 파생된 규칙 (JSON에 없음, 새 ID로 추가 필요):
- 현재 `ELASTICACHE_EC3_NO_RESERVED_NODE` → JSON EC4와 통합
- 현재 `ELASTICACHE_EC4_NO_HA` → 별도 rule ID 신규 등록 필요
- 현재 `ELASTICACHE_EC5_ENGINE_UPGRADE` → 별도 rule ID 신규 등록 필요

---

## ELB (LB1–LB5) ⚠️ SKILL.md ↔ JSON 불일치

JSON 기준 (canonical):

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| LB1 | finding | REVIEW_DELETE | req_count==0, connections==0, processed_bytes==0, zero_days≥28, dependency_checks_clear | **wrong-id** | 구현 있음. dependency_checks_clear 조건 없음 |
| LB2 | review | INVESTIGATE | req_count==0 AND (connections>0 OR healthy_hosts>0 OR dns_dependency OR listener_dependency) | **wrong-id** | 현재 구현 LB2는 low traffic finding (의미 다름) |
| LB3 | finding | OPTIMIZE_OR_SHARE | req_count>0, low_utilization | **wrong-id** | 현재 구현 LB3는 NLB review (의미 다름) |
| LB4 | review | ADD_GOVERNANCE_TAGS | missing Owner/Environment/Purpose tags | **wrong-id** | 현재 구현 LB4는 CLB migration (의미 다름) |
| LB5 | **blocker** | DO_NOT_DELETE_WITHOUT_OWNER | deletion_protection OR dr_role OR blue_green_role | **wrong-id** | 현재 구현 LB5는 stale listener finding (완전히 반대 의미) |

SKILL.md에서 파생된 규칙 (JSON에 없음, 새 ID로 추가 필요):
- `ELB_CLB_MIGRATE` (현재 LB4 역할) → 신규 등록
- `ELB_STALE_LISTENER` (현재 LB5 역할) → 신규 등록
- `ELB_NLB_REVIEW` (현재 LB3 역할) → 신규 등록

---

## RDS (R1–R6) ⚠️ 현재 Python R3·R5·R6 의미 불일치

JSON 기준 (canonical):

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| R1 | finding | REVIEW_SINGLE_AZ | multi_az=true, env in nonprod, no SLA/DR evidence | ok | |
| R2 | finding | REVIEW_DOWNSIZE | cpu_avg<20%, cpu_p95<50%, freeable_memory_safe, io_p95<50%, connections≥1 | stub | freeable_memory·io 조건 누락 |
| R3 | finding | REVIEW_STORAGE_IOPS | provisioned_iops >> observed_p95_iops, storage_free_safe | **wrong-id** | 현재 구현 R3는 RI coverage (R5 역할) |
| R4 | finding | UPGRADE_ENGINE | engine_version past standard support, extended support active | ok | |
| R5 | finding | MODEL_RESERVED_INSTANCE | steady_baseline, reserved_instance_coverage_missing | **wrong-id** | 현재 구현 R5는 gp2→gp3 (JSON에 없는 규칙) |
| R6 | **blocker** | DO_NOT_DOWNSIZE_REVIEW_PERFORMANCE | cpu_peak_high OR mem_low OR swap_high OR io_latency_high OR disk_queue_high OR replica_lag_high | **wrong-id** | 현재 구현 R6는 underused read replica finding (완전히 반대 의미) |

JSON에 없는 규칙 (SKILL.md/Python에서 파생, 별도 ID로 신규 등록 필요):
- `RDS_GP2_TO_GP3` (현재 R5 역할) — 유효한 최적화, 신규 등록
- `RDS_UNDERUSED_REPLICA` (현재 R6 역할) — 유효한 finding, 신규 등록

---

## EBS (S1–S5)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| S1 | finding | REVIEW_DELETE | SourceVolumeStatus==deleted, no dependency evidence | ok | |
| S2 | **blocker** | DO_NOT_DELETE | AMI ref OR AWS Backup OR legal_hold OR DR tag | missing | 구현 없음 — S1과 함께 체크 필요 |
| S3 | finding | CONSIDER_ARCHIVE | age≥90d, retained long-term, restore_freq low | missing | |
| S4 | finding | REVIEW_FSR_DISABLE | fast_snapshot_restore=true, no recent restore evidence | missing | |
| S5 | review | ADD_GOVERNANCE_TAGS | missing Owner/Purpose/RetentionDays/BackupPolicy | missing | |

---

## NAT (N1–N6)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| N1 | finding | ADD_S3_GATEWAY_ENDPOINT | s3_traffic_via_nat_gb>0, no correct S3 gateway endpoint | ok | |
| N2 | finding | ADD_DYNAMODB_GATEWAY_ENDPOINT | dynamodb_traffic_via_nat_gb>0, no correct DDB gateway endpoint | ok | |
| N3 | finding | MODEL_INTERFACE_ENDPOINT | aws_service_traffic_via_nat≥100GB/mo, interface endpoint net savings positive | missing | |
| N4 | finding | REVIEW_AZ_LOCAL_NAT_OR_ENDPOINTS | cross_az_nat_traffic≥50GB/mo | missing | |
| N5 | finding | REVIEW_NAT_REMOVAL | no remaining required egress, endpoints cover all destinations | missing | |
| N6 | finding | FIX_ENDPOINT_CONFIGURATION | endpoint exists but region mismatch OR missing route table OR private DNS misconfigured | missing | |

---

## SQS (Q1–Q5)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| Q1 | finding | ENABLE_LONG_POLLING | receive_wait_time==0, empty_receives≥50/hr OR ratio≥50% | ok | |
| Q2 | finding | REVIEW_CONSUMER_POLLING | receive_wait_time>0, empty_receive_ratio≥50% | missing | |
| Q3 | finding | REVIEW_BATCHING | requests≥10000/day, batch_api_usage low | missing | |
| Q4 | finding | FIX_RETRY_VISIBILITY | message_age_high OR receive_count_high OR dlq_high OR visibility_timeout_low | missing | |
| Q5 | review | VALIDATE_CLIENT_TIMEOUTS | client_read_timeout < wait_time OR unknown | missing | |

---

## TGW (T1–T4)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| T1 | finding | MIGRATE_TGW_TRAFFIC_TO_VPC_PEERING | tgw_data_processing_charges, same-region VPC traffic, peering candidate | ok | |
| T2 | finding | EVALUATE_VPC_PEERING_MIGRATION | attachment_count≤3, no transitive/inspection/multi-account requirement | missing | |
| T3 | finding | REVIEW_IDLE_ATTACHMENT | attachment_bytes<1GB/mo | missing | |
| T4 | finding | REVIEW_AZ_LOCAL_ROUTING | cross-AZ routing via TGW when same-AZ path exists | missing | |

---

## Kinesis (K1–K5)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| K1 | finding | REVIEW_EFO | efo=true, processing_interval≥5min, no latency SLA, no throughput contention | ok | |
| K2 | finding | REDUCE_SHARDS | stream_mode=PROVISIONED, write_p95<50%, read_p95<50%, throttles==0, iterator_age low | missing | |
| K3 | finding | MODEL_BILLING_MODE | traffic pattern suggests mode switch may save | missing | |
| K4 | finding | REVIEW_RETENTION | retention>24hr, no replay/compliance requirement | missing | |
| K5 | **blocker** | DO_NOT_DOWNSIZE_REVIEW_PERFORMANCE | write_throttles>0 OR read_throttles>0 OR iterator_age_p95≥5000ms OR lag_high | missing | 구현 없음 |

---

## Organizations (O1–O5)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| O1 | review | REVIEW_CONSOLIDATED_BILLING | accounts outside billing family, on-demand spend exists | stub | 현재 단순 presence check |
| O2 | review | REVIEW_DISCOUNT_SHARING | RI/SP sharing disabled, stranded commitments + eligible on-demand | missing | |
| O3 | finding | MODEL_RI_SP_PURCHASE | on_demand_pct>40%, commitment_util_model≥80% | missing | |
| O4 | finding | REALIGN_COMMITMENTS | existing_commitment_util<80% | missing | |
| O5 | review | IMPROVE_COST_GOVERNANCE | missing owner/cost_center/env/account_mapping tags | missing | |

---

## CloudWatch (C1–C4)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| C1 | finding | SET_RETENTION | retention_in_days missing OR ==0 | ok | |
| C2 | finding | REDUCE_RETENTION | retention_in_days > env_max, no exception | missing | |
| C3 | finding | REVIEW_DELETE_CANDIDATE | log_bytes_ingested≈0 for ≥30d | missing | |
| C4 | finding | NORMALIZE_TERRAFORM | uses retention_days instead of retention_in_days | missing | |

---

## CloudWatch-Alarm (M1–M4)

| Rule ID | Type | Action | Key Facts | Status | Notes |
|---------|------|--------|-----------|--------|-------|
| M1 | finding | DOWNGRADE_TO_STANDARD | period==1, actual_required_resolution≥60s | ok | |
| M2 | finding | DOWNGRADE_TO_STANDARD | metric_type==high_resolution, evaluation_period_minutes≥1 | ok | |
| M3 | finding | REVIEW_HIGH_RESOLUTION | high_resolution_alarm_count>10, no sub-minute SLA | missing | |
| M4 | finding | NORMALIZE_TERRAFORM | uses resolution_seconds / metric_type instead of period | missing | |

---

## 구현 우선순위 요약

### 🔴 즉시 수정 필요 (wrong-id — 현재 JSON과 충돌)

| 현재 Python ID | JSON ID | 문제 |
|---------------|---------|------|
| RDS_R3_NO_RESERVED_INSTANCE | R3 (storage IOPS) | 의미 완전 다름 |
| RDS_R5_GP2_STORAGE | R5 (RI coverage) | 의미 다름 + R5는 RI여야 함 |
| RDS_R6_UNDERUSED_READ_REPLICA | R6 (blocker!) | finding으로 구현됐으나 JSON은 blocker |
| ELB_LB2_LOW_UTILIZATION | LB2 (review) | finding으로 구현됐으나 JSON은 review |
| ELB_LB3_REVIEW_NLB_DOWNGRADE | LB3 (low traffic finding) | 의미 다름 |
| ELB_LB4_MIGRATE_CLB | LB4 (governance tags review) | 의미 다름 |
| ELB_LB5_STALE_LISTENER | LB5 (blocker!) | finding으로 구현됐으나 JSON은 blocker |
| ECS_E2_EC2_UNDERUTILIZED | E2 (Fargate memory) | 의미 완전 다름 |
| ELASTICACHE_EC3_NO_RESERVED_NODE | EC3 (excess shards) | 의미 완전 다름 |
| ELASTICACHE_EC4_NO_HA | EC4 (RI candidate) | 의미 다름 |
| ELASTICACHE_EC5_ENGINE_UPGRADE | EC5 (blocker!) | finding으로 구현됐으나 JSON은 blocker |

### 🟡 신규 등록 필요 (JSON에 없지만 유효한 규칙)

| 신규 Rule ID | 의미 | 근거 |
|-------------|------|------|
| RDS_GP2_TO_GP3 | gp2 스토리지 → gp3 마이그레이션 | 실제 절감 기회, SKILL.md에서 파생 |
| RDS_UNDERUSED_READ_REPLICA | 미사용 read replica 삭제 | SKILL.md에서 파생 |
| ECS_EC2_LAUNCH_UNDERUTILIZED | EC2 launch type CPU 낮음 | SKILL.md에서 파생 |
| ECS_SCHEDULED_SCALING_MISSING | scheduled scaling 부재 | SKILL.md E4와 유사 (단 JSON E4는 platform version) |
| ELB_CLB_MIGRATE | CLB → ALB 마이그레이션 | SKILL.md LB4에서 파생 |
| ELB_NLB_REVIEW | ALB→NLB 다운그레이드 검토 | SKILL.md LB3에서 파생 |
| ELB_STALE_LISTENER | listener 존재하나 TG 비어있음 | SKILL.md LB5에서 파생 |
| ELASTICACHE_HA_REVIEW | 단일 노드 prod HA 부재 | SKILL.md EC4에서 파생 |
| ELASTICACHE_ENGINE_EOL | EOL 엔진 버전 업그레이드 | SKILL.md EC5에서 파생 |

### 🟢 신규 구현 필요 (JSON에 있으나 graph.py에 없음)

**Blockers (최우선 — 잘못된 절감 방지):**
- S3 V3, DynamoDB D7, EBS S2, Kinesis K5 (각각 DO_NOT_* 액션)

**Key findings (높은 절감 가능성):**
- DynamoDB D4, D5 (GSI 최적화)
- NAT N3–N6
- Kinesis K2, K4
- SQS Q2–Q4
- TGW T2–T4
- CloudWatch C2, C3
- ECS E4 (platform version)
- ElastiCache EC3 (excess shards)

---

*생성일: 2026-06-22*
*대상 파일: `cloudsweep/graph.py`, `.claude/skills/finops-*/rules/*.json`*

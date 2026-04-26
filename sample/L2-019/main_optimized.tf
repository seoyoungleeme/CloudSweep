terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

resource "aws_elasticache_replication_group" "elasticache-replication-group-k1b93b" {
  replication_group_id = "elasticache-replication-group-k1b93b"
  description          = "Redis replication group"

  node_type  = "cache.r5.large"
  # FinOps E1: 노드 수 축소 6 → 2 (HA 최소값)
  # 30일 cache_hit_rate_pct avg=99.9967% / min=99.14% — 메모리 압박 없음
  # CPU avg=8.45%, 연결 avg=49 — 워크로드 경량
  # 초과 4노드 × $0.228/hr × 730h = $665.76/mo 절감
  # automatic_failover_enabled=true이므로 최소 2노드 유지 필요
  num_cache_clusters   = 2
  engine               = "redis"
  engine_version       = "7.0"

  automatic_failover_enabled = true

  port = 6379

  subnet_group_name  = aws_elasticache_subnet_group.elasticache-replication-group-k1b93b.name
  security_group_ids = [aws_security_group.elasticache-replication-group-k1b93b_sg.id]

  tags = {
    Name = "elasticache-replication-group-k1b93b"
  }
}

resource "aws_elasticache_subnet_group" "elasticache-replication-group-k1b93b" {
  name       = "elasticache-replication-group-k1b93b-subnet-group"
  subnet_ids = var.private_subnet_ids
}

# 아래 클러스터는 num_cache_clusters=2, hit rate 91.7%, CPU 54% — 변경 없음 (실제 부하 중)
resource "aws_elasticache_replication_group" "elasticache-replication-group-31362i" {
  replication_group_id = "elasticache-replication-group-31362i"
  description          = "Redis replication group"

  node_type            = "cache.r5.large"
  num_cache_clusters   = 2
  engine               = "redis"
  engine_version       = "7.0"

  automatic_failover_enabled = true

  port = 6379

  subnet_group_name  = aws_elasticache_subnet_group.elasticache-replication-group-31362i.name
  security_group_ids = [aws_security_group.elasticache-replication-group-31362i_sg.id]

  tags = {
    Name = "elasticache-replication-group-31362i"
  }
}

resource "aws_elasticache_subnet_group" "elasticache-replication-group-31362i" {
  name       = "elasticache-replication-group-31362i-subnet-group"
  subnet_ids = var.private_subnet_ids
}

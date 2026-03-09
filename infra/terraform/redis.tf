# infra/terraform/redis.tf

resource "aws_elasticache_subnet_group" "redis_subnet" {
  name       = "${var.cluster_name}-redis-subnet"
  subnet_ids = module.vpc.database_subnets
}

resource "aws_security_group" "redis_sg" {
  name        = "${var.cluster_name}-redis-sg"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr_block] # Internal access only
  }
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "rag-redis-${var.environment}"
  description          = "Redis for RAG Semantic Cache"
  node_type            = "cache.t4g.micro" # Cost effective Graviton
  num_cache_clusters   = 1 # Primary + Replica for HA
  port                 = 6379
  
  subnet_group_name    = aws_elasticache_subnet_group.redis_subnet.name
  security_group_ids   = [aws_security_group.redis_sg.id]
  
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true # Requires SSL/TLS (supported by our python client)
}
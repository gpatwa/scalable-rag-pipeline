# infra/terraform/neo4j.tf

# Security Group: Allow traffic on Bolt Port (7687) and HTTP (7474)
resource "aws_security_group" "neo4j_sg" {
  name        = "neo4j-access-sg"
  description = "Allow internal traffic to Neo4j"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "Internal Bolt Protocol"
    from_port   = 7687
    to_port     = 7687
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr_block] # Only allow VPC traffic
  }

  ingress {
    description = "Internal HTTP"
    from_port   = 7474
    to_port     = 7474
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Note: The actual deployment of Neo4j is handled via Helm in 'deploy/helm/neo4j'.
# That Helm chart will request a Persistent Volume (PVC).
# AWS EKS default StorageClass (gp2) is okay, but for High Budget, we want gp3 or io2.

# We will define a Storage Class in Kubernetes manifests later, 
# relying on the EBS CSI driver installed on EKS.
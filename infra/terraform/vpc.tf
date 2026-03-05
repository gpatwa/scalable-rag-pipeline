# infra/terraform/vpc.tf

# Create the VPC (Virtual Private Cloud)
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws" # Use verified community module
  version = "5.1.0"

  name = "${var.cluster_name}-vpc"
  cidr = var.vpc_cidr

  # Define Availability Zones for High Availability (Multi-AZ)
  azs = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  # Consolidate to a Single Availability Zone for cost saving
  #azs = ["${var.aws_region}a"]

  # PUBLIC SUBNETS: For Load Balancers and NAT Gateways
  public_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]

  # PRIVATE SUBNETS: For EKS Nodes, RDS, and Redis (Security Best Practice)
  private_subnets = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  # DATABASE SUBNETS: Specific isolation for Aurora/Redis
  database_subnets = ["10.0.201.0/24", "10.0.202.0/24", "10.0.203.0/24"]

  # Enable NAT Gateway so private pods can download Docker images/Models from internet
  enable_nat_gateway = true
  single_nat_gateway = true   # 🚨 Forces all AZs to share ONE gateway ($32/mo total)
  one_nat_gateway_per_az = false # cost saving
  
  # Enable DNS hostnames (required for EKS)
  enable_dns_hostnames = true
  enable_dns_support   = true

  # Tag subnets so Kubernetes Load Balancers know where to go
  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
    "karpenter.sh/discovery"          = var.cluster_name # Used by Karpenter
  }
}
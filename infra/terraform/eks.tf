# infra/terraform/eks.tf

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.29" # Use stable K8s version

  authentication_mode  = "API_AND_CONFIG_MAP"
  enable_cluster_creator_admin_permissions = true

  # Networking: Connect to the VPC we just created
  vpc_id                         = module.vpc.vpc_id
  subnet_ids                     = module.vpc.private_subnets
  cluster_endpoint_public_access = true # Allow developer access from internet (secured by IAM)

  # OIDC Provider is REQUIRED for Service Accounts (IRSA)
  # This allows a specific Pod to assume an AWS IAM Role
  enable_irsa = true

  # NODE GROUPS (The "Always On" Baseline)
  eks_managed_node_groups = {
    # System Node Group: Runs CoreDNS, Karpenter, Ingress Controller
    system = {
      name           = "system-nodes"
      instance_types = ["t3a.medium"] # 'a' stands for AMD, which is ~10% cheaper than Intel
      capacity_type  = "SPOT"         # Cuts the compute cost by up to 70%
      disk_size      = 20             # Shrinks the hard drive to 20GB to save on EBS costs
      min_size       = 1
      max_size       = 2
      desired_size   = 1

      # Taints prevent App pods from scheduling here accidentally
      taints = [
        {
          key    = "CriticalAddonsOnly"
          value  = "true"
          effect = "NO_SCHEDULE"
        }
      ]
    }

    # App Node Group: Runs API, Qdrant, Neo4j pods
    # Separate from system nodes so app pods have a place to schedule
    app = {
      name           = "app-nodes"
      instance_types = ["t3a.medium"]  # Dev: burstable (prod: m6i.large+)
      capacity_type  = "SPOT"          # SPOT for dev cost savings (~$11/mo)
      disk_size      = 30
      min_size       = 1
      max_size       = 3               # Dev cap (prod: 10+)
      desired_size   = 1
    }
  }

  # Prepare security groups
  node_security_group_tags = {
    "karpenter.sh/discovery" = var.cluster_name
  }
}

# Export the Cluster Endpoint
output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}
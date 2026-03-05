# infra/terraform/rds.tf

module "aurora" {
  source  = "terraform-aws-modules/rds-aurora/aws"
  version = "8.3.0"

  name           = "${var.cluster_name}-postgres"
  engine         = "aurora-postgresql"
  engine_version = "15.15"
  
  # SERVERLESS V2: Scales Compute (ACU) up/down based on load
  instance_class = "db.serverless" 
  
  instances = {
    one = {}
    #two = {} # High Availability (2 instances) save cost
  }

  # Dev/Learning: Minimal baseline, scales up only under load
  # Saves ~$65/mo vs min_capacity=2 (prod: raise to 2+ and max to 64)
  serverlessv2_scaling_configuration = {
    min_capacity = 0.5 # Lowest ACU — nearly pauses when idle (~$22/mo baseline)
    max_capacity = 8   # Sufficient for dev workloads, prevents runaway cost
  }

  vpc_id               = module.vpc.vpc_id
  db_subnet_group_name = module.vpc.database_subnet_group_name
  security_group_rules = {
    vpc_ingress = {
      cidr_blocks = [module.vpc.vpc_cidr_block] # Allow only internal VPC access
    }
  }

  master_username = "ragadmin"
  master_password = var.db_password
  
  skip_final_snapshot = true # Always snapshot before deleting
}
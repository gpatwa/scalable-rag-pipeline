# infra/terraform/iam.tf

# 1. IAM Policy for the Ingestion Pipeline (Ray Workers)
resource "aws_iam_policy" "ingestion_policy" {
  name        = "RAG_Ingestion_S3_Policy"
  description = "Allows Ray workers to read/write documents bucket"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Effect   = "Allow"
        Resource = [
          aws_s3_bucket.documents.arn,
          "${aws_s3_bucket.documents.arn}/*"
        ]
      }
    ]
  })
}

# 2. IAM Role for Service Account (IRSA) - Binds K8s SA to AWS Role
module "ingestion_irsa_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "rag-ingestion-role"
  
  # Trust relationship: Only the 'ray-worker' service account in 'default' ns can use this
  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["default:ray-worker"]
    }
  }

  role_policy_arns = {
    policy = aws_iam_policy.ingestion_policy.arn
  }
}

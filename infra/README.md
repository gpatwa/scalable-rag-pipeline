# infra/README.md

# Infrastructure

This directory contains all Infrastructure as Code (IaC) definitions required to run the RAG platform on AWS. It uses **Terraform** to provision cloud resources and **Karpenter** for Kubernetes node autoscaling.

## Core Components

The Terraform configuration in `terraform/` provisions the following key resources:

-   **Networking (`vpc.tf`):** A secure, multi-AZ Virtual Private Cloud (VPC) with public and private subnets.
-   **Kubernetes (`eks.tf`):** A managed Amazon EKS cluster that serves as the foundation for all our services.
-   **Databases (`rds.tf`, `redis.tf`, `neo4j.tf`):**
    -   An AWS Aurora (PostgreSQL) Serverless v2 cluster for chat history.
    -   An AWS ElastiCache (Redis) cluster for semantic caching and rate limiting.
    -   Security groups and prerequisites for a self-hosted Neo4j cluster.
-   **Storage (`s3.tf`):** An S3 bucket configured with versioning and Transfer Acceleration for document uploads.
-   **Permissions (`iam.tf`):** Fine-grained IAM Roles for Service Accounts (IRSA) to ensure pods have least-privilege access to AWS resources.

The Karpenter configuration in `karpenter/` defines:

-   **Provisioners:** Rules that allow Karpenter to dynamically launch Spot or On-Demand EC2 instances (`g5.xlarge` for GPUs, `m6i.large` for CPUs) based on pod resource requests.

## Prerequisites

Before you begin, ensure you have the following tools installed and configured:

1.  **Terraform CLI** (`>= 1.5.0`)
2.  **AWS CLI** (configured with credentials that have permission to create the resources)
3.  **kubectl**
4.  **Helm**

## Usage

### Recommended Method (Makefile)

The simplest way to provision the infrastructure is to use the `Makefile` command from the root of the repository.

```bash
# This command will navigate to the terraform directory, initialize it, and apply the configuration.
make infra
```

### Manual Steps

If you need more control, you can run the Terraform commands manually:

1.  **Navigate to the Terraform directory:**
    ```bash
    cd infra/terraform
    ```

2.  **Initialize Terraform:**
    This downloads the necessary providers and configures the S3 backend.
    ```bash
    terraform init
    ```

3.  **Plan the changes:**
    This shows you what resources will be created, modified, or destroyed.
    ```bash
    terraform plan -var="db_password=your_secure_password"
    ```

4.  **Apply the configuration:**
    This will create the resources in your AWS account.
    ```bash
    terraform apply -var="db_password=your_secure_password" -auto-approve
    ```

## State Management

The Terraform state is stored remotely in an **S3 bucket** and uses a **DynamoDB table** for locking. This is an industry best practice that prevents conflicts when multiple team members are managing the same infrastructure. The configuration for this is in `infra/terraform/main.tf`.

## Tearing Down

To destroy all resources managed by Terraform and avoid ongoing costs, you can use the comprehensive cleanup script from the root directory:

```bash
# This script handles Helm uninstalls and then runs terraform destroy.
./scripts/cleanup.sh
```

Alternatively, to destroy only the Terraform resources:

```bash
cd infra/terraform
terraform destroy -auto-approve
```
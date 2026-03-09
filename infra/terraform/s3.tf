# infra/terraform/s3.tf

resource "aws_s3_bucket" "documents" {
  bucket = "rag-platform-documents-${var.environment}-1" # Unique per environment

  # Force Destroy is FALSE for production data safety
  force_destroy = true # for development 

  tags = {
    Name = "Documents Bucket"
  }
}

# Enable Versioning: If a user overwrites a file, we keep the old one
resource "aws_s3_bucket_versioning" "docs_ver" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Transfer Acceleration: Disabled for dev (saves per-GB fees)
# Enable for production with global users uploading large files
resource "aws_s3_bucket_accelerate_configuration" "docs_accel" {
  bucket = aws_s3_bucket.documents.id
  status = "Suspended" # Change to "Enabled" for production
}

# Lifecycle Rule: Move old raw files to cheaper storage (Intelligent Tiering)
resource "aws_s3_bucket_lifecycle_configuration" "docs_lifecycle" {
  bucket = aws_s3_bucket.documents.id

  rule {
    id     = "archive-old-files"
    status = "Enabled"

    filter {} # Required by AWS provider >= 4.x (empty = apply to all objects)

    transition {
      days          = 30
      storage_class = "INTELLIGENT_TIERING" # Auto-optimizes cost
    }
  }
}

# CORS Rule: Allow Browser (Frontend) to upload directly to S3
resource "aws_s3_bucket_cors_configuration" "docs_cors" {
  bucket = aws_s3_bucket.documents.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "POST", "GET"]
    allowed_origins = ["https://your-rag-domain.com"] # Restrict to your domain
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}
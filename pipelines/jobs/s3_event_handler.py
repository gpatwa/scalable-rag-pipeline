# pipelines/jobs/s3_event_handler.py
import boto3
import os
import time
from ray.job_submission import JobSubmissionClient

# Config
RAY_ADDRESS = os.getenv("RAY_ADDRESS", "http://rag-ray-cluster-head-svc:8265")
S3_BUCKET = os.getenv("S3_BUCKET_NAME")

def handle_s3_event(event, context):
    """
    AWS Lambda entry point (or called via SQS poller).
    Triggered when a file is uploaded to S3.
    """
    # 1. Parse Event
    # Assuming standard S3 Event structure
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        
        print(f"File uploaded: s3://{bucket}/{key}")
        
        # 2. Submit Ray Job
        # We don't process it here (Lambda has 15m timeout).
        # We tell the Ray Cluster to process it (can take hours).
        submit_ingestion_job(bucket, key)

def submit_ingestion_job(bucket: str, file_key: str):
    """
    Submits a job to the Ray Cluster via REST API.
    """
    client = JobSubmissionClient(RAY_ADDRESS)
    
    # The command runs inside the Ray Head node
    # It executes the 'main.py' pipeline we wrote in Module 4
    job_id = client.submit_job(
        entrypoint=f"python pipelines/ingestion/main.py {bucket} {file_key}",
        
        # Working dir contains our pipeline code
        runtime_env={
            "working_dir": "./", 
            "pip": ["boto3", "qdrant-client", "neo4j", "langchain", "unstructured"]
        }
    )
    
    print(f"Submitted Ray Job ID: {job_id}")
    return job_id

if __name__ == "__main__":
    # Local test simulation
    fake_event = {
        "Records": [{
            "s3": {
                "bucket": {"name": "rag-docs"},
                "object": {"key": "manuals/engine_v8.pdf"}
            }
        }]
    }
    handle_s3_event(fake_event, None)
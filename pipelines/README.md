# pipelines/README.md

# Data Pipelines

This directory contains the asynchronous data ingestion and processing logic. This is the "factory" that populates our databases with knowledge.

## Contents

-   **`ingestion/`**: The main Ray Data pipeline. It is responsible for:
    1.  Reading raw files (PDF, DOCX, HTML) from S3.
    2.  Parsing and chunking the text.
    3.  Generating vector embeddings.
    4.  Extracting a knowledge graph (entities and relationships).
    5.  Indexing the data into Qdrant (vectors) and Neo4j (graph).
-   **`jobs/`**: Scripts and definitions for triggering these pipelines. The `s3_event_handler.py` is designed to be run as an AWS Lambda function that listens for S3 upload events and submits a job to the Ray cluster.

## Usage

The pipeline is triggered automatically when a file is uploaded to the designated S3 bucket. It can also be triggered manually for batch processing by submitting a job to the Ray Job Submission API.
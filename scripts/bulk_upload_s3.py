# scripts/bulk_upload_s3.py
import boto3
import os
import sys
import threading
from boto3.s3.transfer import TransferConfig

def upload_directory(dir_path, bucket_name):
    """
    High-performance S3 uploader.
    """
    s3 = boto3.client('s3')
    
    # Configure multipart upload
    config = TransferConfig(
        multipart_threshold=1024 * 25, # 25MB
        max_concurrency=20, # 20 threads
        multipart_chunksize=1024 * 25,
        use_threads=True
    )

    files_to_upload = []
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            local_path = os.path.join(root, file)
            # Maintain folder structure in S3
            s3_path = os.path.relpath(local_path, dir_path)
            files_to_upload.append((local_path, s3_path))

    print(f"Found {len(files_to_upload)} files. Starting upload...")

    def upload_file(args):
        local, remote = args
        try:
            print(f"Uploading {remote}...")
            s3.upload_file(local, bucket_name, remote, Config=config)
        except Exception as e:
            print(f"Failed to upload {remote}: {e}")

    # Use ThreadPool to blast files
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=10) as executor:
        executor.map(upload_file, files_to_upload)

    print("✅ Bulk upload finished.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python bulk_upload_s3.py <local_dir> <bucket_name>")
        sys.exit(1)
    
    upload_directory(sys.argv[1], sys.argv[2])
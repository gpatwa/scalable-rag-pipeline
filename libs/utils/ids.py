# libs/utils/ids.py
import uuid
import hashlib

def generate_session_id() -> str:
    """Generate a standard UUID for chat sessions"""
    return str(uuid.uuid4())

def generate_file_id(content: bytes) -> str:
    """
    Generate a deterministic ID based on file content.
    Prevents uploading the exact same file twice.
    """
    return hashlib.md5(content).hexdigest()

def generate_trace_id() -> str:
    """Generate ID for OpenTelemetry traces"""
    return uuid.uuid4().hex
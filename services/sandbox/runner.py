# services/sandbox/runner.py
from flask import Flask, request, jsonify
import sys
import io
import contextlib
import multiprocessing

app = Flask(__name__)

def execute_code_safe(code: str, queue):
    """
    Runs code in a separate process to allow hard timeouts.
    Captures stdout.
    """
    # Redirect stdout to capture print() statements
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            # Dangerous! Only run this in isolated container.
            # Restricted globals can add slight safety layer.
            exec(code, {"__builtins__": __builtins__}, {})
        queue.put({"status": "success", "output": buffer.getvalue()})
    except Exception as e:
        queue.put({"status": "error", "output": str(e)})

@app.route("/execute", methods=["POST"])
def run_code():
    data = request.json
    code = data.get("code", "")
    timeout = data.get("timeout", 5) # 5 seconds max

    queue = multiprocessing.Queue()
    p = multiprocessing.Process(target=execute_code_safe, args=(code, queue))
    p.start()
    
    # Block until timeout
    p.join(timeout)
    
    if p.is_alive():
        p.terminate()
        return jsonify({"output": "Error: Execution timed out."}), 408
        
    if not queue.empty():
        result = queue.get()
        return jsonify(result)
        
    return jsonify({"output": "No output produced."})

if __name__ == "__main__":
    # Run on port 8080
    app.run(host="0.0.0.0", port=8080)
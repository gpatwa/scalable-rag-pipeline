# scripts/load_test.py
from locust import HttpUser, task, between
import os

class RAGUser(HttpUser):
    # Wait 1 to 5 seconds between tasks
    wait_time = between(1, 5)
    
    @task
    def chat_stream_task(self):
        """
        Simulates a user sending a chat message.
        """
        headers = {
            "Authorization": f"Bearer {os.getenv('AUTH_TOKEN')}" # Load token from env
        }
        
        # Example query
        payload = {
            "message": "What is the warranty policy for the new X1 processor?",
            "session_id": "loadtest-user-123"
        }
        
        # Use streaming=True to handle the SSE response
        with self.client.post(
            "/api/v1/chat/stream", 
            json=payload, 
            headers=headers, 
            stream=True,
            name="/chat/stream" # Group results under this name
        ) as response:
            if response.status_code != 200:
                response.failure("Failed request")
            else:
                # Iterate through the stream to simulate a real client
                for line in response.iter_lines():
                    if line:
                        pass # In a real test, you might validate the JSON
                response.success()
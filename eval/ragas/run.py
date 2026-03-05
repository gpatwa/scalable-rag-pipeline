# eval/ragas/run.py
import os
import pandas as pd
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from datasets import Dataset

# In a real setup, you would load these from 'eval/datasets/golden.json'
# and your system's actual outputs.

def run_evaluation(questions: list, answers: list, contexts: list, ground_truths: list):
    """
    Runs the Ragas evaluation suite.
    """
    # 1. Prepare Dataset
    data = {
        "question": questions,
        "answer": answers,
        "contexts": contexts, # List of lists of strings (retrieved docs)
        "ground_truth": ground_truths
    }
    dataset = Dataset.from_dict(data)

    # 2. Run Evaluation
    # Ragas uses OpenAI by default, ensure OPENAI_API_KEY is set
    # or configure it to use your Ray Serve endpoint via LangChain wrapper.
    print("Starting Ragas Evaluation...")
    
    results = evaluate(
        dataset=dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
    )

    # 3. Export Report
    df = results.to_pandas()
    output_path = "eval/reports/latest.csv"
    df.to_csv(output_path, index=False)
    
    print(f"✅ Evaluation complete. Results saved to {output_path}")
    print(results)

if __name__ == "__main__":
    # More complex data for demonstration
    run_evaluation(
        questions=[
            "What is Kubernetes?",
            "Who maintains Kubernetes?",
            "What is the purpose of Kubernetes?"
        ],
        answers=[
            "Kubernetes is an open-source container orchestration platform.",
            "Kubernetes is maintained by the Cloud Native Computing Foundation.",
            "Kubernetes is used for automating deployment, scaling, and management of containerized applications."
        ],
        contexts=[
            [
                "Kubernetes is an open-source system for automating deployment, scaling, and management of containerized applications.",
                "It was originally designed by Google and is now maintained by the Cloud Native Computing Foundation."
            ],
            [
                "The Cloud Native Computing Foundation (CNCF) is responsible for maintaining Kubernetes.",
                "Kubernetes was donated to the CNCF by Google in 2015."
            ],
            [
                "Kubernetes helps in managing containerized applications across a cluster of machines.",
                "It provides features like load balancing, scaling, and self-healing of applications."
            ]
        ],
        ground_truths=[
            "Kubernetes is an open-source container orchestration platform.",
            "Kubernetes is maintained by the Cloud Native Computing Foundation.",
            "Kubernetes is used for automating deployment, scaling, and management of containerized applications."
        ]
    )
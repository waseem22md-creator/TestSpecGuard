
import ollama

response = ollama.chat(
    model="qwen2.5-coder:1.5b",
    messages=[
        {
            "role": "user",
            "content": (
                "Write a Python function named add "
                "that returns the sum of two integers. "
                "Return only the code."
            )
        }
    ]
)

print(response["message"]["content"])

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastapi",
#   "uvicorn",
#   "requests",
#   "python-dotenv",
#   "pytesseract",
#   "tesseract",
#   "numpy",
#   "pillow",
#   "scikit-learn",
#   "textwrap3",
# ]
# ///
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import json
import subprocess
from dotenv import load_dotenv
import tempfile
import pytesseract
from PIL import Image
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
# from sentence_transformers import SentenceTransformer
import textwrap


app = FastAPI()
load_dotenv()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=['GET','POST'],
    allow_headers=["*"],
)
AIPROXY_TOKEN = os.getenv("AIPROXY_TOKEN")
# print(AIPROXY_TOKEN)
tools=[
    {
        "type":"function",
        "function":{
            "name":"script_runner",
            "description":"Install a package and run a script from a url with provided arguments.",
            "parameters":{
                "type":"object",
                "properties":{
                    "script_url":{
                        "type":"string",
                        "description":"The url of the script to run."
                    },
                    "args":{
                        "type":"array",
                        "items":{
                            "type":"string",
                    },
                    "description":"The arguments to pass to the script."
                    },
                },
                "required":["script_url", "args"]
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name":"task_runner",
            "description": "Generate and run code for specific task.",
            "parameters":{
                "type":"object",
                "properties":{
                    "task":{
                        "type":"string",
                        "description":"The generated concise python code."
                    },
                    "args":{
                        "type":"array",
                        "items":{
                            "type":"string",
                        },
                        "description":"The arguments to be used in the code."
                    }
                },
                "required":["task", "args"]
            }
        }
    }

]
@app.get("/")
def home():
    return {"message": "Hello World"}

@app.get("/read")
def read_file(path :str):
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return {"error": "File not found"}, 404
    
@app.post("/run")
def run_task(task: str):
    url = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {AIPROXY_TOKEN}"
    }

    data ={
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role":"user",
                "content":task
            },
            {
                "role":"system",
                "content":"""
You are an assistant responsible for executing tasks.
- If a script URL is provided, use script_runner.
- Otherwise, use task_runner to generate a self-contained Python script that: 
  - Includes necessary imports and follows best practices.
  - Determines the base directory dynamically using os.getcwd().
  - Constructs all file paths with os.path.join() for cross-platform compatibility
  - If the task is count number of particular day from dates. Don't restrict with one date format. Use all date formats.
  - For reading the credit card number, don't write all numbers in image but only in same line with 16 digits. Don't use cv2
"""
            }
        ],
        "tools":tools,
        "tool_choice":"auto"
    }
    response = requests.post(url=url, headers=headers, json=data)
    # return response.json()['choices'][0]['message']['tool_calls'][0]['function']['name']
    if response.json()['choices'][0]['message']['tool_calls'][0]['function']['name'] == "script_runner":
        arguments = json.loads(response.json()['choices'][0]['message']['tool_calls'][0]['function']['arguments'])
        script_url = arguments['script_url']
        email = arguments['args'][0]

        # Extract script filename from URL (e.g., datagen.py)
        # script_name = script_url.split("/")[-1]

        # # Use curl to download the script
        # curl_command = f"curl -o {script_name} {script_url}"
        # subprocess.run(curl_command, shell=True, check=True)
        # with open(script_name, "r") as f:
        #     content = f.read().replace("/data", "./data")

        # with open(script_name, "w") as f:
        #     f.write(content)

        # Run the downloaded script using uv
        command = ["uv", "run", script_url, email]
        subprocess.run(command)

        return {"message": f"Script {script_url} executed successfully with argument {email}"}

    elif response.json()['choices'][0]['message']['tool_calls'][0]['function']['name'] == "task_runner":
        # return response.json()
        arguments = json.loads(response.json()['choices'][0]['message']['tool_calls'][0]['function']['arguments'])
        task = arguments['task']
        formatted_task = textwrap.dedent(task).strip()
        if any(forbidden in formatted_task for forbidden in ["/etc/", "/home/", "/Users/", "/var/", "/bin/"]):
            raise HTTPException(status_code=403, detail="Unauthorized file access attempt")
        print(formatted_task)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", encoding="utf-8", delete=False) as temp_script:
            temp_script.write(formatted_task)
            temp_script_path = temp_script.name

        try:
        # Run the script using uv
            command = ["uv", "run", temp_script_path]
            subprocess.run(command, check=True)
        finally:
        # Remove the temporary file after execution
            os.remove(temp_script_path)
        return {"message": f"Task {task} executed successfully"}
    else:
        return {"message": "Task not supported"}, 400


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
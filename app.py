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
#   "uuid",
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
import uuid


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
You are an assistant responsible for executing tasks efficiently and securely.
-If a script URL is provided, use script_runner to download and execute the script.
-Otherwise, use task_runner to generate a self-contained Python script that:
    -Includes necessary imports and follows best coding practices.
    -Determines the base directory dynamically using os.getcwd().
    -Constructs all file paths using os.path.join() to ensure cross-platform compatibility.
    -If the task involves counting occurrences of a particular weekday from dates, support multiple date formats, ensuring flexibility in parsing.
    -If the task involves extracting a credit card number from an image, only extract 16-digit numbers found on the same line, without using cv2.
    -Ensures all required dependencies are installed. If a module is missing, install it dynamically using:
    try:
        import some_module
    except ImportError:
        import subprocess
        subprocess.run(["pip", "install", "some_module"], check=True)
        import some_module
    -If the task involves extracting an email ID from a text file containing email content, do not extract the first email found. Instead, identify and extract the specific email ID mentioned in the task.
"""
            }
        ],
        "tools":tools,
        "tool_choice":"auto"
    }
    response = requests.post(url=url, headers=headers, json=data)
    # print("Status Code:", response.status_code)
    # print("Response Text:", response.text)
    # # return response.json()['choices'][0]['message']['tool_calls'][0]['function']['name']
    # print(response.json())
    if response.json()['choices'][0]['message']['tool_calls'][0]['function']['name'] == "script_runner":
        arguments = json.loads(response.json()['choices'][0]['message']['tool_calls'][0]['function']['arguments'])
        script_url = arguments['script_url']
        email = arguments['args'][0]

        # Extract script filename from URL (e.g., datagen.py)
        script_name = script_url.split("/")[-1]
        # print (script_name)
        # Use curl to download the script
        curl_command = f"curl -o {script_name} {script_url}"
        subprocess.run(curl_command, shell=True, check=True)
        data_dir = "./data"
        os.makedirs(data_dir, exist_ok=True)
        os.chmod(data_dir, 0o777)

        with open(script_name, "r") as f:
            content = f.read()
        content = content.replace('"/data"', '"./data"').replace("'/data'", "'./data'").replace("/data", "./data")
        

        with open(script_name, "w") as f:
            f.write(content)

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
        # print(formatted_task)
        temp_script_path = os.path.join(tempfile.gettempdir(), f"task_{uuid.uuid4().hex}.py")
        with open(temp_script_path, "w", encoding="utf-8") as temp_script:
            temp_script.write(formatted_task)

        try:
        # Run the script using uv
            command = ["uv", "run", temp_script_path]
            subprocess.run(command, check=True)
        except Exception as e:
            return {"error": str(e)}, 500
        return {"message": f"Task {task} executed successfully"}
    else:
        return {"message": "Task not supported"}, 400


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
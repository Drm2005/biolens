import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI API KEY is not found")

client = genai.Client(api_key=api_key)
for model in client.models.list():
    print(model.name)

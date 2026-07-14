from dotenv import load_dotenv
from groq import Groq
import os


load_dotenv()
client = Groq(
    api_key=os.environ.get("GROQ_API_KEY"),
)

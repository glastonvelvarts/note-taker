import google.generativeai as genai
import os
from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

def summarize_transcript(transcript: str):
    prompt = f"""
    Summarize the following meeting transcript into:
    - Key points
    - Decisions made
    - Action items
    Transcript:
    {transcript}
    """
    response = model.generate_content(prompt)
    return response.text

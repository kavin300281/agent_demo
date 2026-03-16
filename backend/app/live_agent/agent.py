import os

from dotenv import load_dotenv
from google.adk.agents import Agent

load_dotenv()

MODEL_NAME = os.getenv("DEMO_AGENT_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")

root_agent = Agent(
    name="live_voice_agent",
    model=MODEL_NAME,
    instruction=(
        "You are a concise, helpful realtime voice assistant. "
        "Respond naturally. Keep responses brief unless asked for detail."
    ),
)

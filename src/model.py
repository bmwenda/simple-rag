import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def get_chat_model() -> ChatOpenAI:
    """Create the chat model used by the RAG answer-generation layer."""

    api_key = os.getenv("OPENAI_API_KEY")
    model_id = os.getenv("OPENAI_MODEL")

    return ChatOpenAI(
        model=model_id,
        api_key=api_key,
        max_retries=2,
        timeout=30,
    )

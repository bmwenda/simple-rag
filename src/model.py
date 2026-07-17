import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

load_dotenv()


def get_chat_model() -> ChatOpenAI:
    """Create the chat model used by the RAG answer-generation layer."""

    api_key = _get_required_env("OPENAI_API_KEY")
    model_id = _get_required_env("OPENAI_MODEL")

    return ChatOpenAI(
        model=model_id,
        api_key=SecretStr(api_key),
        max_retries=2,
        timeout=30,
    )


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

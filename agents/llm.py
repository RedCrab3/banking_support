import os

from langchain_openai import ChatOpenAI


def build_model():
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = (
        os.getenv("OPENAI_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
    )

    if not api_key or not base_url:
        raise RuntimeError("Lab API configuration is missing.")

    return ChatOpenAI(
        model="gpt-4o-mini",
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        max_tokens=300,
        timeout=30,
        max_retries=0,
        use_responses_api=False,
    )
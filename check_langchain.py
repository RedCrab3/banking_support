import os
import time

from langchain_openai import ChatOpenAI


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = (
        os.getenv("OPENAI_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
    )

    if not api_key or not base_url:
        raise RuntimeError("Lab API configuration is missing.")

    model = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        max_tokens=30,
        timeout=30,
        max_retries=0,
        use_responses_api=False,
    )

    started = time.perf_counter()

    response = model.invoke([
        (
            "human",
            "Reply with exactly: LangChain connection successful.",
        )
    ])

    print("Reply:", response.content)
    print("Model:", response.response_metadata.get("model_name"))
    print("Usage:", response.usage_metadata)
    print("Elapsed seconds:", round(time.perf_counter() - started, 2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        message = str(exc)
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            message = message.replace(api_key, "[REDACTED]")

        print(f"Connection failed ({type(exc).__name__}): {message}")
        raise SystemExit(1)
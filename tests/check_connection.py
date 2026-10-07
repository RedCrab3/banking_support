import os
import time

from openai import OpenAI


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = (
        os.getenv("OPENAI_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
    )

    if not api_key or not base_url:
        raise RuntimeError(
            "Lab API configuration is missing from this terminal."
        )

    started = time.perf_counter()

    with OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=30.0,
        max_retries=0,
    ) as client:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Reply with exactly: "
                        "Banking assistant connection successful."
                    ),
                }
            ],
            temperature=0,
            max_tokens=20,
        )

    print("Reply:", response.choices[0].message.content)
    print("Model:", response.model)

    if response.usage:
        print("Total tokens:", response.usage.total_tokens)

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
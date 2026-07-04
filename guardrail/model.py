import os

from dotenv import load_dotenv
from groq import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    Groq,
    GroqError,
    RateLimitError,
)

load_dotenv()
_client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def call_model(prompt: str) -> str:
    """Send prompt to the Groq model and return the reply text (or a failure string)."""
    try:
        response = _client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except AuthenticationError:
        return "Model call failed: invalid or missing GROQ_API_KEY."
    except RateLimitError:
        return "Model call failed: rate limit hit, try again shortly."
    except (APIConnectionError, APITimeoutError):
        return "Model call failed: network error reaching Groq."
    except GroqError as e:
        return f"Model call failed: {e}"

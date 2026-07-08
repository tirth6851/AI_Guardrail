"""
Groq model call. The only network dependency in the core.

CHANGE FROM THE ORIGINAL: call_model used to RETURN the failure message as a
plain string ("Model call failed: ..."). That string then flowed straight into
judge_output, which would classify our own error text and could hand it back to
the user as if it were the model's answer. Now a failure is a distinct, typed
outcome (ModelResult.ok == False) so the pipeline can branch on it and NEVER
present an error as an answer or waste an output-judge call on it.
"""
import os
from dataclasses import dataclass

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

MODEL_NAME = "llama-3.3-70b-versatile"


@dataclass
class ModelResult:
    ok: bool          # True = `text` is a real model answer; False = `text` is an error reason
    text: str


def call_model(prompt: str) -> ModelResult:
    """Send prompt to Groq. Return ModelResult(ok=True, answer) or ModelResult(ok=False, reason)."""
    try:
        response = _client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
        )
        return ModelResult(True, response.choices[0].message.content)
    except AuthenticationError:
        return ModelResult(False, "invalid or missing GROQ_API_KEY")
    except RateLimitError:
        return ModelResult(False, "rate limit hit, try again shortly")
    except (APIConnectionError, APITimeoutError):
        return ModelResult(False, "network error reaching Groq")
    except GroqError as e:
        return ModelResult(False, str(e))

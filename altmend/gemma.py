"""Talk to Gemma 4 about an image.

Two ways to reach the model:
  * Google AI Studio (Gemini API) with an API key  -> the default
  * Any OpenAI-compatible server (Ollama, vLLM, llama.cpp, OpenRouter)
    by passing --base-url, so the whole tool can run on your own machine.
"""

import base64
import os
from pathlib import Path

import requests

MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".heic": "image/heic",
}

DEFAULT_MODEL = "gemma-4-31b-it"


class ImageUnreadable(Exception):
    """The picture could not be loaded, so there is nothing to describe."""


class ModelUnavailable(Exception):
    """The model refused the request or could not be reached."""


def mime_type_for(source: str) -> str:
    suffix = Path(source.split("?")[0]).suffix.lower()
    return MIME_TYPES.get(suffix, "image/png")


def read_image_bytes(source: str, document: Path, timeout: int = 30) -> bytes:
    """Load a local image relative to the document, or download a remote one."""
    if source.lower().startswith(("http://", "https://")):
        try:
            answer = requests.get(source, timeout=timeout)
            answer.raise_for_status()
            return answer.content
        except requests.RequestException as problem:
            raise ImageUnreadable(f"could not download {source}: {problem}") from problem

    candidate = (document.parent / source).resolve()
    if not candidate.is_file():
        raise ImageUnreadable(f"file not found: {candidate}")
    return candidate.read_bytes()


class GemmaVision:
    """A thin wrapper so the rest of the tool does not care which backend is used."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 90,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout = timeout
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self._google_client = None

        if self.base_url is None and not self.api_key:
            raise ModelUnavailable(
                "No API key found. Set GEMINI_API_KEY, or point --base-url at a local "
                "Gemma server such as Ollama (http://localhost:11434/v1)."
            )

    # Gemma on the Gemini API does not accept a separate system instruction,
    # so the whole brief travels with the image in one user turn.
    def describe(self, image_bytes: bytes, mime_type: str, instruction: str) -> str:
        if self.base_url:
            return self._ask_openai_compatible(image_bytes, mime_type, instruction)
        return self._ask_gemini_api(image_bytes, mime_type, instruction)

    def _ask_gemini_api(self, image_bytes: bytes, mime_type: str, instruction: str) -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError as problem:
            raise ModelUnavailable(
                "google-genai is not installed. Run: pip install google-genai"
            ) from problem

        if self._google_client is None:
            self._google_client = genai.Client(api_key=self.api_key)

        try:
            answer = self._google_client.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    instruction,
                ],
            )
        except Exception as problem:  # the SDK raises several unrelated error types
            raise ModelUnavailable(str(problem)) from problem

        text = (answer.text or "").strip()
        if not text:
            raise ModelUnavailable("the model returned an empty answer")
        return text

    def _ask_openai_compatible(self, image_bytes: bytes, mime_type: str, instruction: str) -> str:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
                        {"type": "text", "text": instruction},
                    ],
                }
            ],
        }

        try:
            answer = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            answer.raise_for_status()
            body = answer.json()
        except requests.RequestException as problem:
            raise ModelUnavailable(f"{self.base_url} did not answer: {problem}") from problem
        except ValueError as problem:
            raise ModelUnavailable("the server replied with something that is not JSON") from problem

        try:
            return body["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as problem:
            raise ModelUnavailable(f"unexpected reply shape: {body}") from problem

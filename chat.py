"""Interactive Gemini chat using Google's current GenAI SDK."""

from __future__ import annotations

import os
from typing import Protocol

DEFAULT_MODEL = "gemini-3.5-flash"


class GeminiResponse(Protocol):
    @property
    def text(self) -> str | None: ...


class GeminiChat(Protocol):
    def send_message(self, message: str) -> GeminiResponse: ...


class GeminiChats(Protocol):
    def create(self, *, model: str) -> GeminiChat: ...


class GeminiClient(Protocol):
    @property
    def chats(self) -> GeminiChats: ...


class ChatSession:
    """Keep conversational context in a Gemini SDK chat session."""

    def __init__(
        self,
        client: GeminiClient | None = None,
        model: str | None = None,
    ) -> None:
        self.model = model or os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL

        if client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is not set. Add a Gemini API key to your "
                    "environment before using AI chat."
                )
            try:
                from google import genai
            except ImportError as error:
                raise RuntimeError(
                    "The Gemini SDK is missing. Install the project with "
                    "`python -m pip install -e .`."
                ) from error

            client = genai.Client(api_key=api_key)

        # Keep the client alive for as long as its chat uses the HTTP transport.
        self._client = client
        self._chat = self._client.chats.create(model=self.model)

    def reply(self, prompt: str) -> str:
        """Send a message in the current conversation and return its reply."""
        from google.genai.errors import APIError

        prompt = prompt.strip()
        if not prompt:
            raise ValueError("The prompt must not be empty.")

        try:
            result = self._chat.send_message(prompt)
        except APIError as error:
            raise RuntimeError(f"Gemini request failed (HTTP {error.code}).") from error

        response = (result.text or "").strip()
        if not response:
            raise RuntimeError("Gemini returned an empty response.")

        return response


def main() -> int:
    """Run a text chat in the terminal."""
    try:
        chat = ChatSession()
    except RuntimeError as error:
        print(f"Unable to start Gemini chat: {error}")
        return 1

    print("Friday is ready. Type 'bye' to exit.")
    while True:
        try:
            prompt = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return 0

        if prompt.lower() in {"bye", "exit", "quit"}:
            print("Goodbye.")
            return 0
        if not prompt:
            continue

        try:
            response = chat.reply(prompt)
        except RuntimeError as error:
            print(f"Friday: {error}")
            continue
        except KeyboardInterrupt:
            print("\nGoodbye.")
            return 0
        print(f"Friday: {response}")


if __name__ == "__main__":
    raise SystemExit(main())

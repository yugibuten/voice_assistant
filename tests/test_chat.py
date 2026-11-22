from __future__ import annotations

import unittest
import weakref
from unittest.mock import Mock, patch

from google import genai
from google.genai import types
from google.genai.errors import ClientError

from chat import ChatSession, main


class ChatSessionTests(unittest.TestCase):
    def test_session_keeps_the_sdk_client_alive(self) -> None:
        client = genai.Client(api_key="offline-test-key")
        client_ref = weakref.ref(client)
        chat = ChatSession(client=client)
        del client

        retained_client = client_ref()
        self.assertIsNotNone(retained_client)
        response = types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        role="model", parts=[types.Part(text="Hello.")]
                    )
                )
            ]
        )
        with patch.object(
            retained_client.models, "generate_content", return_value=response
        ):
            self.assertEqual(chat.reply("Hello"), "Hello.")

    def test_replies_reuse_the_default_model_chat_and_trim_output(self) -> None:
        client = Mock()
        send_message = client.chats.create.return_value.send_message
        send_message.side_effect = [
            Mock(text="  Hello.  "),
            Mock(text="You said your name is Friday."),
        ]
        with patch.dict("os.environ", {"GEMINI_MODEL": ""}):
            chat = ChatSession(client=client)

        self.assertEqual(chat.reply(" Hi "), "Hello.")
        self.assertEqual(chat.reply("What did I say?"), "You said your name is Friday.")

        client.chats.create.assert_called_once_with(model="gemini-3.5-flash")
        self.assertEqual(
            [call.args for call in send_message.call_args_list],
            [("Hi",), ("What did I say?",)],
        )

    def test_empty_prompt_is_rejected_without_calling_client(self) -> None:
        client = Mock()
        chat = ChatSession(client=client)

        with self.assertRaises(ValueError):
            chat.reply("  ")

        client.chats.create.return_value.send_message.assert_not_called()

    def test_terminal_chat_continues_after_a_gemini_error(self) -> None:
        client = Mock()
        client.chats.create.return_value.send_message.side_effect = [
            ClientError(429, {"error": {"message": "Quota exceeded"}}),
            Mock(text="Hello again."),
        ]
        with (
            patch("chat.ChatSession", return_value=ChatSession(client=client)),
            patch("builtins.input", side_effect=["Hello", "Try again", "bye"]),
            patch("builtins.print") as output,
        ):
            self.assertEqual(main(), 0)

        output.assert_any_call("Friday: Gemini request failed (HTTP 429).")
        output.assert_any_call("Friday: Hello again.")

    def test_missing_key_fails_with_setup_guidance(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                ChatSession()


if __name__ == "__main__":
    unittest.main()

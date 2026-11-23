from __future__ import annotations

import unittest
from array import array
from threading import Event
from unittest.mock import Mock, patch

from google import genai
from google.genai import types

from chat import ChatSession
from desktop import _voice_level
from main import YugiAssistant, get_weather, listen_command, run_voice, safe_calculate


class CalculatorTests(unittest.TestCase):
    def test_evaluates_basic_arithmetic_and_parentheses(self) -> None:
        self.assertEqual(safe_calculate("12 * (4 + 3)"), 84)
        self.assertEqual(safe_calculate("-3 + 0.5"), -2.5)

    def test_rejects_code_and_oversized_exponents(self) -> None:
        for expression in (
            "__import__('os').system('echo unsafe')",
            "True + 1",
            "2 ** 101",
            "(-1) ** 0.5",
        ):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    safe_calculate(expression)

    def test_rejects_division_by_zero(self) -> None:
        with self.assertRaises(ZeroDivisionError):
            safe_calculate("1 / 0")


class WeatherTests(unittest.TestCase):
    def test_looks_up_location_then_returns_fahrenheit(self) -> None:
        location_response = Mock()
        location_response.json.return_value = {
            "results": [{"name": "London", "latitude": 51.5, "longitude": -0.1}]
        }
        weather_response = Mock()
        weather_response.json.return_value = {"current": {"temperature_2m": 68.0}}

        with patch(
            "requests.get",
            side_effect=[location_response, weather_response],
        ) as get:
            self.assertEqual(get_weather("London"), ("London", 68.0))

        self.assertEqual(get.call_count, 2)
        self.assertEqual(
            get.call_args_list[1].kwargs["params"]["temperature_unit"],
            "fahrenheit",
        )

    def test_unknown_city_has_a_clear_error(self) -> None:
        location_response = Mock()
        location_response.json.return_value = {"results": []}

        with patch("requests.get", return_value=location_response):
            with self.assertRaisesRegex(ValueError, "No location found"):
                get_weather("Unknown place")


class VoiceAudioTests(unittest.TestCase):
    def test_louder_samples_produce_a_larger_orb_signal(self) -> None:
        def pcm(amplitude: int) -> bytes:
            return array("h", [amplitude, -amplitude] * 220).tobytes()

        self.assertEqual(_voice_level(b""), 0)
        self.assertEqual(_voice_level(pcm(0)), 0)
        self.assertLess(_voice_level(pcm(300)), _voice_level(pcm(3000)))
        self.assertEqual(_voice_level(pcm(30000)), 1)

    def test_microphone_reports_samples_before_transcription_and_resets(self) -> None:
        samples = b"\x00\x01" * 1024
        observed: list[bytes] = []
        source = Mock()
        source.stream.read.return_value = samples
        recognizer = Mock()
        audio = Mock()

        def listen(source, **kwargs):
            self.assertEqual(source.stream.read(1024), samples)
            self.assertEqual(observed, [samples])
            return audio

        recognizer.listen.side_effect = listen
        recognizer.recognize_google.return_value = "Hey Yugi"
        with (
            patch("speech_recognition.Recognizer", return_value=recognizer),
            patch("speech_recognition.Microphone") as microphone,
        ):
            microphone.return_value.__enter__.return_value = source
            self.assertEqual(listen_command(observed.append), "Hey Yugi")

        self.assertEqual(observed, [samples, b""])
        recognizer.recognize_google.assert_called_once_with(audio, language="en-IN")


class AssistantTests(unittest.TestCase):
    def test_voice_keeps_context_when_woken_again(self) -> None:
        def response(message: str) -> types.GenerateContentResponse:
            return types.GenerateContentResponse(
                candidates=[
                    types.Candidate(
                        content=types.Content(
                            role="model", parts=[types.Part(text=message)]
                        )
                    )
                ]
            )

        stop = Event()
        spoken: list[str] = []
        statuses: list[str] = []
        follow_up = "What were the two colors?"

        def speak(message: str) -> None:
            spoken.append(message)
            if message == "Blue and green.":
                stop.set()

        with (
            genai.Client(api_key="offline-test-key") as client,
            patch.object(
                client.models,
                "generate_content",
                side_effect=[
                    response("I remember blue."),
                    response("I remember green too."),
                    response("Blue and green."),
                ],
            ) as generate,
            patch("main.ChatSession", return_value=ChatSession(client=client)) as chat,
            patch(
                "main.listen_command",
                side_effect=[
                    "Ignore this before activation",
                    "Hey Yugi, remember blue",
                    "Also remember green",
                    "Bye",
                    f"Hey Yu Gi, {follow_up}",
                ],
            ),
        ):
            run_voice(
                speaker=speak,
                show_status=lambda state, label: statuses.append(state),
                stop=stop,
                return_to_standby=True,
            )

        chat.assert_called_once()
        contents = generate.call_args.kwargs["contents"]
        self.assertEqual(
            [(turn.role, turn.parts[0].text) for turn in contents],
            [
                ("user", "remember blue"),
                ("model", "I remember blue."),
                ("user", "Also remember green"),
                ("model", "I remember green too."),
                ("user", follow_up),
            ],
        )
        self.assertEqual(statuses.count("standby"), 2)
        self.assertIn("thinking", statuses)
        self.assertIn("speaking", statuses)
        self.assertEqual(spoken[-1], "Blue and green.")

    def test_goodbye_stops_the_assistant(self) -> None:
        spoken: list[str] = []
        assistant = YugiAssistant(speaker=spoken.append)

        self.assertFalse(assistant.handle_command("bye"))
        self.assertEqual(spoken, ["I will be back."])

    def test_general_prompt_uses_gemini_session(self) -> None:
        class FakeChatSession:
            def reply(self, prompt: str) -> str:
                return f"Answer: {prompt}"

        spoken: list[str] = []
        assistant = YugiAssistant(
            speaker=spoken.append,
            chat_session=FakeChatSession(),
        )

        self.assertTrue(assistant.handle_command("Explain time complexity"))
        self.assertEqual(spoken, ["Answer: Explain time complexity"])

    def test_time_command_uses_the_clock(self) -> None:
        spoken: list[str] = []
        assistant = YugiAssistant(speaker=spoken.append)

        self.assertTrue(assistant.handle_command("What time is it?"))
        self.assertRegex(spoken[0], r"^The time is \d{2}:\d{2}\.$")


if __name__ == "__main__":
    unittest.main()

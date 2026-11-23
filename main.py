"""Cross-platform Yugi voice assistant."""

from __future__ import annotations

import ast
import datetime as dt
import math
import operator
import os
import re
import subprocess
import sys
from collections.abc import Callable
from functools import cache
from pathlib import Path
from threading import Event
from typing import Protocol

from chat import ChatSession

_BINARY_OPERATORS: dict[
    type[ast.operator], Callable[[int | float, int | float], int | float]
] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[int | float], int | float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_AUDIO_SUFFIXES = (".mp3", ".m4a", ".ogg", ".wav", ".flac")


class SpeechEngine(Protocol):
    def say(self, message: str) -> None: ...

    def runAndWait(self) -> None: ...


class ChatResponder(Protocol):
    def reply(self, prompt: str) -> str: ...


def safe_calculate(expression: str) -> int | float:
    """Evaluate basic arithmetic without executing arbitrary Python code."""
    expression = expression.strip()
    if not expression or len(expression) > 256:
        raise ValueError("Enter an arithmetic expression of at most 256 characters.")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise ValueError("That is not a valid arithmetic expression.") from error

    if sum(1 for _ in ast.walk(tree)) > 64:
        raise ValueError("That expression is too complex.")

    def evaluate(node: ast.expr) -> int | float:
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            result = node.value
        elif isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            result = _UNARY_OPERATORS[type(node.op)](evaluate(node.operand))
        elif isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Exponents must be between -100 and 100.")
            result = _BINARY_OPERATORS[type(node.op)](left, right)
        else:
            raise ValueError("Only basic arithmetic is supported.")

        if type(result) not in {int, float}:
            raise ValueError("The result must be a real number.")
        if isinstance(result, float) and not math.isfinite(result):
            raise ValueError("The result is outside the supported numeric range.")
        if isinstance(result, int) and result.bit_length() > 4096:
            raise ValueError("The result is outside the supported numeric range.")
        return result

    return evaluate(tree.body)


def get_weather(city_name: str) -> tuple[str, float]:
    """Look up a city's current temperature in Fahrenheit using Open-Meteo."""
    city_name = city_name.strip()
    if not city_name:
        raise ValueError("Enter a city name.")

    import requests

    try:
        location_response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city_name, "count": 1, "language": "en", "format": "json"},
            timeout=10,
        )
        location_response.raise_for_status()
        locations = location_response.json().get("results") or []
        if not locations:
            raise ValueError(f"No location found for {city_name!r}.")

        location = locations[0]
        weather_response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "current": "temperature_2m",
                "temperature_unit": "fahrenheit",
            },
            timeout=10,
        )
        weather_response.raise_for_status()
        temperature = weather_response.json()["current"]["temperature_2m"]
    except requests.RequestException as error:
        raise RuntimeError(f"Weather service request failed: {error}") from error
    except (KeyError, TypeError, IndexError) as error:
        raise RuntimeError(
            "The weather service returned an unexpected response."
        ) from error

    return str(location.get("name", city_name)), float(temperature)


@cache
def _speech_engine() -> SpeechEngine:
    import pyttsx3

    return pyttsx3.init()


def speak(message: str) -> None:
    """Speak using the operating system's default speech driver."""
    engine = _speech_engine()
    engine.say(message)
    engine.runAndWait()


def listen_command(on_pcm: Callable[[bytes], None] | None = None) -> str | None:
    """Listen for one command; return None if speech could not be understood."""
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        if on_pcm is not None:
            read = source.stream.read

            def read_with_meter(size: int) -> bytes:
                samples = read(size)
                on_pcm(samples)
                return samples

            source.stream.read = read_with_meter
        print("Listening...")
        recognizer.pause_threshold = 1
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=12)
        except sr.WaitTimeoutError:
            print("No speech detected.")
            return None
        finally:
            if on_pcm is not None:
                on_pcm(b"")

    try:
        query = recognizer.recognize_google(audio, language="en-IN")
    except sr.UnknownValueError:
        print("Sorry, I could not understand that.")
        return None
    except sr.RequestError as error:
        raise RuntimeError(f"Speech recognition service failed: {error}") from error

    print(f"You: {query}")
    return query.strip()


def _open_music(track: str) -> None:
    music_directory = Path(os.getenv("MUSIC_DIR", "~/Music")).expanduser()
    track = track.strip().strip("\"'")
    if not track or "/" in track or "\\" in track:
        raise ValueError("Give a song name, not a path.")
    if music_directory.is_dir():
        candidate = music_directory / track
        if not candidate.suffix:
            candidate = next(
                (
                    music_directory / f"{track}{suffix}"
                    for suffix in _AUDIO_SUFFIXES
                    if (music_directory / f"{track}{suffix}").is_file()
                ),
                candidate,
            )
    else:
        candidate = music_directory / track

    if not candidate.is_file() or candidate.suffix.lower() not in _AUDIO_SUFFIXES:
        raise FileNotFoundError(
            f"Could not find '{track}' in {music_directory}. "
            "Set MUSIC_DIR to your music folder."
        )

    if sys.platform == "win32":
        os.startfile(str(candidate))  # type: ignore[attr-defined]
    else:
        command = (
            ["open", str(candidate)]
            if sys.platform == "darwin"
            else ["xdg-open", str(candidate)]
        )
        subprocess.Popen(command)


class YugiAssistant:
    """Dispatch voice commands while initializing optional services on demand."""

    def __init__(
        self,
        speaker: Callable[[str], None] = speak,
        chat_session: ChatResponder | None = None,
    ) -> None:
        self._speak = speaker
        self._chat_session = chat_session

    def handle_command(self, query: str) -> bool:
        """Handle a command; return False when the assistant should exit."""
        query = query.strip()
        lowered = query.lower()

        if not query:
            return True
        if lowered in {"bye", "goodbye", "exit", "quit"}:
            self._speak("I will be back.")
            return False
        if lowered.rstrip("?!.,") in {
            "time",
            "current time",
            "what time is it",
            "what is the time",
            "tell me the time",
        }:
            self._speak(f"The time is {dt.datetime.now():%H:%M}.")
        elif lowered.startswith("calculate"):
            try:
                answer = safe_calculate(query[len("calculate") :])
            except (ArithmeticError, ValueError) as error:
                self._speak(f"I could not calculate that: {error}")
            else:
                self._speak(f"The answer is {answer}.")
        elif "weather" in lowered:
            city = lowered.split("weather", 1)[1].strip()
            if city.startswith("in "):
                city = city[3:].strip()
            if not city:
                self._speak("Say weather in, followed by the city name.")
                return True
            try:
                name, temperature = get_weather(city)
            except (RuntimeError, ValueError) as error:
                self._speak(f"I could not get the weather: {error}")
            else:
                self._speak(f"It is {temperature:g} degrees Fahrenheit in {name}.")
        elif "joke" in lowered:
            import pyjokes

            self._speak(pyjokes.get_joke())
        elif "wikipedia" in lowered or lowered.startswith("who is "):
            import wikipedia

            topic = lowered.replace("wikipedia", "").replace("who is", "").strip()
            if not topic:
                self._speak("Please say what you want me to search for.")
            else:
                try:
                    summary = wikipedia.summary(topic, sentences=2)
                except wikipedia.exceptions.DisambiguationError as error:
                    choices = ", ".join(error.options[:5])
                    self._speak(
                        f"That topic is ambiguous. Try one of these: {choices}."
                    )
                except wikipedia.exceptions.PageError:
                    self._speak("I could not find a Wikipedia page for that topic.")
                else:
                    self._speak(f"According to Wikipedia: {summary}")
        elif lowered.startswith("play music"):
            track = query[len("play music") :].strip()
            if not track:
                self._speak("Say play music, followed by the song name.")
                return True
            try:
                _open_music(track)
            except (FileNotFoundError, OSError, ValueError) as error:
                self._speak(f"I could not play that song: {error}")
            else:
                self._speak("Playing music.")
        elif lowered in {"how are you", "how are you?"}:
            self._speak("I am fine, thank you. How are you?")
        elif lowered in {"fine", "good", "i am fine", "i'm fine"}:
            self._speak("It is good to know that you are doing well.")
        else:
            try:
                if self._chat_session is None:
                    self._chat_session = ChatSession()
                response = self._chat_session.reply(query)
            except RuntimeError as error:
                self._speak(f"I could not answer that: {error}")
            else:
                self._speak(response)

        return True


def run_voice(
    *,
    speaker: Callable[[str], None],
    show_status: Callable[[str, str], None],
    stop: Event,
    return_to_standby: bool = False,
    on_pcm: Callable[[bytes], None] | None = None,
) -> None:
    """Run hands-free voice input with one chat session for the entire window."""

    def speak_with_status(message: str) -> None:
        if not stop.is_set():
            show_status("speaking", "Speaking")
            speaker(message)

    assistant = YugiAssistant(speaker=speak_with_status)
    active = False
    show_status("standby", "Say “Hey Yugi”")
    while not stop.is_set():
        query = listen_command(on_pcm)
        if not query or stop.is_set():
            continue
        if not active:
            wake = re.search(r"\bhey\s+yu\s*gi\b", query, re.IGNORECASE)
            if wake is None:
                continue
            active = True
            query = query[wake.end() :].lstrip(" ,.!?")
            if not query:
                speak_with_status("I’m listening.")
                show_status("listening", "Listening")
                continue
        show_status("thinking", "Thinking")
        if not assistant.handle_command(query):
            if not return_to_standby:
                return
            active = False
            show_status("standby", "Say “Hey Yugi”")
        else:
            show_status("listening", "Listening")


def main() -> int:
    """Open the desktop assistant or start voice mode in the terminal."""
    if sys.platform == "darwin" and "--terminal" not in sys.argv[1:]:
        from desktop import run_desktop

        return run_desktop(run_voice)

    def show_status(state: str, message: str) -> None:
        if state == "standby":
            print(message)

    try:
        run_voice(speaker=speak, show_status=show_status, stop=Event())
    except (ImportError, OSError, RuntimeError, AttributeError) as error:
        print(f"Yugi could not start or continue voice mode: {error}")
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

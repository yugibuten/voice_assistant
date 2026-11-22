# Friday Voice Assistant

A cross-platform Python voice assistant with Gemini 3.5 Flash chat, speech recognition and
playback, Wikipedia summaries, jokes, weather, music playback, and safe basic
arithmetic. Text chat can be used without a microphone.

## Requirements

- Python 3.11 or newer
- A Gemini API key for AI chat
- A microphone and audio playback support for voice features

## Install

Create and activate a virtual environment, then install the project and its
voice dependencies:

```bash
python -m venv .venv
```

On macOS/Linux:

```bash
source .venv/bin/activate
python -m pip install -e ".[voice,dev]"
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[voice,dev]"
```

If you only want text chat, install without the voice extra:

```bash
python -m pip install -e .
```

The `voice` extra installs the assistant features; microphone access additionally
requires PortAudio and PyAudio. Install the system audio prerequisite for your
operating system, then add the microphone extra:

```bash
python -m pip install -e ".[microphone]"
```

On macOS, install PortAudio with `brew install portaudio` first. For other
platforms, follow the
[SpeechRecognition microphone installation guide](https://github.com/Uberi/speech_recognition#pyaudio-for-microphone-users).

## Configure Gemini

Create your own API key in
[Google AI Studio](https://aistudio.google.com/apikey). Set it in the current
shell; do not paste it into source files or commit it.

macOS/Linux:

```bash
export GEMINI_API_KEY="your-key"
```

Windows PowerShell:

```powershell
$env:GEMINI_API_KEY = "your-key"
```

Friday uses Gemini 3.5 Flash (`gemini-3.5-flash`) by default in both text and
voice chat. Set `GEMINI_MODEL` to use a different model available to your API
key. The Google Gen AI SDK keeps the conversation history in memory and sends
it with each new chat message. Restart Friday to begin a new conversation.

## Run

Text chat:

```bash
python -m chat
```

Voice assistant:

```bash
python main.py
```

On macOS, this opens a small window with an animated orb. The orb changes as
Friday listens, thinks, and speaks. The rings expand and ripple with the volume
of your microphone and Friday's spoken replies. Say **“Hey Friday”** to activate
it, or say **“Hey Friday, what time is it?”** to activate it and give a command
together.
Say **“Bye”** to return to standby. Gemini remembers previous turns when you
wake Friday again while the window is open. Closing the window clears that
session's conversation history.

On other platforms, Friday runs voice mode in the terminal. On macOS, use
`python main.py --terminal` to run voice mode without opening the window.

Try commands such as:

- “What time is it?”
- “Calculate 12 * (4 + 3)”
- “Weather in London”
- “Who is Ada Lovelace?”
- “Tell me a joke”
- “Play music [song name]”
- “Explain recursion with a simple example”
- “Bye”

Set `MUSIC_DIR` to the folder containing your music files. Without it, Friday
looks in `~/Music`. Weather uses Open-Meteo and does not require an API key.
Speech recognition uses Google's online recognition service.

## Development

Run the focused tests and lint checks:

```bash
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
```

## Credential safety

The original source contained an API credential and a WolframAlpha app ID.
Those values have been removed from the current files, but may remain in Git
history. Revoke or rotate any credentials that were previously committed, and
avoid sharing credentials in chat or source control.

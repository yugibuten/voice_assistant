"""Native macOS window for Yugi's voice status."""

from __future__ import annotations

import json
import math
import subprocess
import wave
from array import array
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread

_ORB_HTML = """
<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Yugi</title>
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; }
  body {
    display: grid; place-items: center; color: #dddafa;
    background: radial-gradient(ellipse at 50% 44%, #201338, #0d0a1b 58%, #080710);
    font: 14px -apple-system, BlinkMacSystemFont, sans-serif;
  }
  canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
  p {
    position: absolute; bottom: 24px; margin: 0 24px; text-align: center;
    letter-spacing: .04em;
  }
</style>
<canvas aria-hidden="true"></canvas>
<p role="status">Say “Hey Yugi”</p>
<script>
  const canvas = document.querySelector('canvas');
  const ctx = canvas.getContext('2d');
  const statusText = document.querySelector('p');
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const hues = {standby: 265, listening: 190, thinking: 281, speaking: 219, error: 350};
  let mode = 'standby';
  let level = 0, targetLevel = 0;
  let w, h;
  const stars = Array.from({length: 86}, () => [
    Math.random(), Math.random(), Math.random()
  ]);
  window.yugiStatus = (state, label) => {
    mode = state;
    targetLevel = 0;
    statusText.textContent = label;
  };
  window.yugiAudioLevel = value => { targetLevel = value; };
  function resize() {
    const pixelRatio = window.devicePixelRatio || 1;
    w = canvas.clientWidth;
    h = canvas.clientHeight;
    canvas.width = w * pixelRatio;
    canvas.height = h * pixelRatio;
    ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  }
  function frame(ms) {
    const hue = hues[mode];
    const t = motion.matches ? 0 : ms / 1000;
    level += (targetLevel - level) * (targetLevel > level ? .5 : .19);
    const voice = level * (motion.matches ? 5 : 28);
    const x = w / 2, y = h * .45, r = Math.min(w, h) * .25 + voice * .25;
    ctx.clearRect(0, 0, w, h);
    for (const [sx, sy, seed] of stars) {
      const alpha = .23 + .16 * Math.sin(t * .8 + seed * 31);
      ctx.fillStyle = 'rgba(222,214,255,' + alpha + ')';
      ctx.beginPath();
      ctx.arc(w * sx, h * sy, .45 + seed * .85, 0, Math.PI * 2);
      ctx.fill();
    }
    const halo = ctx.createRadialGradient(x, y, 0, x, y, r * 1.65);
    halo.addColorStop(0, 'hsla(' + hue + ',87%,64%,.36)');
    halo.addColorStop(.58, 'hsla(' + hue + ',91%,57%,.22)');
    halo.addColorStop(1, 'transparent');
    ctx.fillStyle = halo;
    ctx.fillRect(0, 0, w, h);
    for (let ring = 0; ring < 6; ring++) {
      ctx.beginPath();
      for (let step = 0; step <= 120; step++) {
        const a = step * Math.PI / 60;
        const ripple = Math.sin(a * (3 + ring) + t * 6 + ring);
        const radius = r + (ring - 2.5) * 3 + ripple * voice * (.43 + ring * .1);
        const px = x + Math.cos(a) * radius;
        const py = y + Math.sin(a) * radius;
        if (step === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.closePath();
      ctx.strokeStyle = 'hsla(' + (hue + ring * 9) + ',94%,74%,'
        + (.18 + ring * .09) + ')';
      ctx.lineWidth = ring === 3 ? 1.75 : .8;
      ctx.stroke();
    }
    requestAnimationFrame(frame);
  }
  addEventListener('resize', resize);
  resize();
  requestAnimationFrame(frame);
</script>
"""


def _voice_level(pcm: bytes) -> float:
    """Map signed 16-bit PCM to a display level with a quiet noise floor."""
    if not pcm:
        return 0.0
    samples = array("h", pcm)
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    decibels = 20 * math.log10(max(1.0, rms) / 32768)
    return min(1.0, max(0.0, (decibels + 52) / 40))


def _speak_on_mac(message: str, on_pcm: Callable[[bytes], None], stop: Event) -> None:
    """Synthesize speech once and meter the same PCM sent to the speakers."""
    import pyaudio

    with TemporaryDirectory() as directory:
        path = Path(directory) / "speech.wav"
        subprocess.run(
            [
                "/usr/bin/say",
                "-f",
                "-",
                "-o",
                str(path),
                "--file-format=WAVE",
                "--data-format=LEI16@22050",
            ],
            input=message + "\n",
            text=True,
            check=True,
        )
        if stop.is_set():
            return
        with wave.open(str(path), "rb") as audio:
            if not audio.getnframes():
                raise RuntimeError("macOS speech synthesis produced no audio.")
            output = pyaudio.PyAudio()
            try:
                block_size = audio.getframerate() // 50
                with closing(
                    output.open(
                        format=pyaudio.paInt16,
                        channels=audio.getnchannels(),
                        rate=audio.getframerate(),
                        frames_per_buffer=block_size,
                        output=True,
                    )
                ) as stream:
                    while not stop.is_set() and (pcm := audio.readframes(block_size)):
                        stream.write(pcm)
                        on_pcm(pcm)
                    stream.stop_stream()
            finally:
                output.terminate()
                on_pcm(b"")


def run_desktop(run_voice: Callable[..., None]) -> int:
    """Run the macOS window on the main thread and voice I/O on a worker."""
    try:
        import AppKit
        import WebKit
        from Foundation import NSObject
        from PyObjCTools import AppHelper
    except ImportError:
        print(
            'Install the desktop dependencies with python -m pip install -e ".[voice]"'
        )
        return 1

    stop = Event()
    app = AppKit.NSApplication.sharedApplication()

    def update_status(state: str, label: str) -> None:
        if not stop.is_set():
            arguments = json.dumps([state, label])
            view.evaluateJavaScript_completionHandler_(
                f"window.yugiStatus(...{arguments})", None
            )

    def update_level(level: float) -> None:
        if not stop.is_set():
            view.evaluateJavaScript_completionHandler_(
                f"window.yugiAudioLevel({level:.4f})", None
            )

    def voice_worker() -> None:
        def show_status(state: str, label: str) -> None:
            AppHelper.callAfter(update_status, state, label)

        def on_pcm(pcm: bytes) -> None:
            if not stop.is_set():
                AppHelper.callAfter(update_level, _voice_level(pcm))

        try:
            run_voice(
                speaker=lambda message: _speak_on_mac(message, on_pcm, stop),
                show_status=show_status,
                stop=stop,
                return_to_standby=True,
                on_pcm=on_pcm,
            )
        except ImportError:
            show_status("error", "Install the voice and microphone extras and reopen.")
        except (
            OSError,
            RuntimeError,
            AttributeError,
            subprocess.SubprocessError,
            wave.Error,
        ) as error:
            print(f"Yugi voice mode stopped: {error}")
            show_status("error", "Voice unavailable. Check the terminal for details.")

    class YugiWindowDelegate(NSObject):
        def webView_didFinishNavigation_(self, web_view, navigation):
            if not worker.is_alive() and worker.ident is None:
                worker.start()

        def windowWillClose_(self, notification):
            stop.set()
            app.terminate_(None)

    worker = Thread(target=voice_worker, name="Yugi voice", daemon=True)
    delegate = YugiWindowDelegate.alloc().init()
    bounds = AppKit.NSMakeRect(0, 0, 360, 360)
    style = AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable
    window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        bounds, style, AppKit.NSBackingStoreBuffered, False
    )
    view = WebKit.WKWebView.alloc().initWithFrame_(bounds)
    view.setNavigationDelegate_(delegate)
    window.setDelegate_(delegate)
    window.setContentView_(view)
    window.setTitle_("Yugi")
    window.center()
    view.loadHTMLString_baseURL_(_ORB_HTML, None)
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)
    app.run()
    return 0

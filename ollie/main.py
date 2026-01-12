#!/usr/bin/env python3
"""OLLIE Voice Assistant - Main entry point with full voice interaction."""

import asyncio
import signal
import sys
import time
from typing import Optional

import numpy as np
from rich.console import Console
from rich.panel import Panel

from .core import Orchestrator
from .core.config import get_settings
from .voice.tts import TTS
from .voice.stt import STT
from .voice.wakeword_oww import OpenWakeWordDetector
from .voice.audio import AudioCapture
from .skills import (
    TimerSkill,
    JokesSkill,
    WeatherSkill,
    TravelSkill,
    ConversionsSkill,
    FlightsSkill,
    RecipesSkill,
    MathSkill,
    SonosSkill,
    ClaudeSkill,
    TimeSkill,
    AircraftSkill,
    SportsSkill,
)


class OllieAssistant:
    """Main voice assistant class."""

    def __init__(self) -> None:
        self.console = Console()
        self.settings = get_settings()
        self.orchestrator = Orchestrator()
        self.tts: Optional[TTS] = None
        self.stt: Optional[STT] = None
        self.wakeword: Optional[OpenWakeWordDetector] = None
        self.audio: Optional[AudioCapture] = None
        self._running = False

        # State
        self._listening = False
        self._wake_detected = False

    async def setup(self) -> None:
        """Initialize all components."""
        self.console.print("[dim]Initializing OLLIE...[/dim]")

        # Register skills
        self.orchestrator.register(TimerSkill(on_timer_complete=self._on_timer))
        self.orchestrator.register(JokesSkill())
        self.orchestrator.register(WeatherSkill())
        self.orchestrator.register(TravelSkill())
        self.orchestrator.register(ConversionsSkill())
        self.orchestrator.register(FlightsSkill())
        self.orchestrator.register(RecipesSkill())
        self.orchestrator.register(MathSkill())
        self.orchestrator.register(SonosSkill())
        self.orchestrator.register(ClaudeSkill())
        self.orchestrator.register(TimeSkill())
        self.orchestrator.register(AircraftSkill())
        self.orchestrator.register(SportsSkill())

        # Initialize TTS
        if self.settings.tts_enabled:
            self.tts = TTS()
            if self.tts.piper_available:
                self.console.print("[dim]  TTS: Piper ready[/dim]")
            else:
                self.console.print("[yellow]  TTS: Piper not available[/yellow]")
                self.tts = None

        # Initialize STT
        self.stt = STT(model_size=self.settings.whisper_model_size)
        self.console.print("[dim]  STT: Loading Whisper model...[/dim]")
        await self.stt.load()
        if self.stt.model:
            self.console.print("[dim]  STT: Whisper ready[/dim]")
        else:
            self.console.print("[yellow]  STT: Whisper not available[/yellow]")

        # Initialize wake word detector (openWakeWord - much faster than Whisper)
        # Use custom "Hey Ollie" model if available, otherwise fall back to hey_jarvis
        import os
        custom_model = os.path.expanduser("~/ollie/models/hey_ollie.onnx")
        use_custom = os.path.exists(custom_model)
        self.wakeword = OpenWakeWordDetector(
            wake_word="hey_jarvis",  # Fallback to pre-trained model
            threshold=0.5 if not use_custom else 0.3,
            on_wake=self._on_wake,
            audio_device="hw:3,0",  # XVF3800
            custom_model_path=custom_model if use_custom else None,
        )
        self.console.print("[dim]  Wake word: Loading openWakeWord...[/dim]")
        await self.wakeword.load()
        await self.wakeword.start()
        self._wake_phrase = "Hey Ollie" if use_custom else "Hey Jarvis"
        if self.wakeword.model:
            self.console.print(f"[dim]  Wake word: Say '{self._wake_phrase}' to wake[/dim]")
        else:
            self.console.print("[yellow]  Wake word: Not available (press Enter to speak)[/yellow]")

        # Audio capture is handled by the wakeword detector's arecord stream
        # No separate AudioCapture needed

    def _on_timer(self, timer) -> None:
        """Handle timer completion."""
        self.console.print(f"\n🔔 [bold yellow]Timer complete: {timer.name}![/bold yellow]")
        if self.tts:
            asyncio.create_task(self.tts.speak(f"Timer {timer.name} is complete!"))

    def _on_wake(self) -> None:
        """Handle wake word detection."""
        self._wake_detected = True
        self.console.print("[bold green]Listening...[/bold green]")

    async def speak(self, text: str) -> None:
        """Speak text using TTS, pausing wake word detection to avoid echo."""
        if self.tts:
            # Pause wake word detection during speech to avoid picking up our own voice
            if self.wakeword:
                self.wakeword.pause()

            await self.tts.speak(text)

            # Wait for audio to fully finish playing + decay
            await asyncio.sleep(0.5)

            # Flush all buffered audio captured during speech (our own voice)
            if self.wakeword:
                self.wakeword.flush_audio_buffer()
                self.wakeword.resume()

    async def listen(self, timeout: float = 5.0, clear_buffer: bool = False) -> str:
        """Listen for speech and transcribe.

        Uses the wakeword detector's arecord stream for audio capture.
        """
        if not self.stt or not self.wakeword:
            return ""

        start_time = time.time()
        audio_chunks = []
        silence_start = None
        speech_detected = False
        silence_threshold = 1.5  # seconds of silence to stop (after speech detected)
        min_speech_chunks = 30  # ~2 seconds of audio before silence can stop
        max_volume = 0  # Debug: track max volume seen

        # Pause wake word detection while listening
        self.wakeword.pause()

        while time.time() - start_time < timeout:
            # Read audio from the wakeword detector's arecord stream
            chunk = self.wakeword._read_audio_chunk()
            if chunk is not None:
                audio_chunks.append(chunk)

                # Voice activity detection - int16 range is -32768 to 32767
                volume = np.abs(chunk).mean()
                max_volume = max(max_volume, volume)

                # XVF3800 beamformed output: typical speech mean ~80-100, silence ~2-5
                if volume > 30:  # Speech detected
                    speech_detected = True
                    silence_start = None
                elif volume < 10:  # Silence
                    if silence_start is None:
                        silence_start = time.time()
                    # Stop after we've heard speech and have enough audio
                    elif speech_detected and len(audio_chunks) > min_speech_chunks:
                        if time.time() - silence_start > silence_threshold:
                            break

            await asyncio.sleep(0.01)

        # Resume wake word detection
        self.wakeword.resume()

        print(f"[Listen] max_volume={max_volume:.0f}, chunks={len(audio_chunks)}, speech={speech_detected}")

        if not audio_chunks:
            return ""

        # Combine and normalize audio
        audio = np.concatenate(audio_chunks, axis=0).flatten()
        audio_float = audio.astype(np.float32) / 32768.0

        # Transcribe
        text = await self.stt.transcribe(audio_float, sample_rate=16000)
        return text

    async def process_query(self, query: str) -> None:
        """Process a user query and respond."""
        if not query.strip():
            return

        self.console.print(f"[bold green]You[/bold green]: {query}")

        result = await self.orchestrator.process(query)

        if result.success:
            self.console.print(f"[bold blue]OLLIE[/bold blue]: {result.response}")
        else:
            self.console.print(f"[bold red]OLLIE[/bold red]: {result.response}")

        # Speak the response
        speak_text = result.speak if result.speak else result.response
        await self.speak(speak_text)

    async def run(self) -> None:
        """Main voice assistant loop."""
        await self.setup()

        self.console.print()
        self.console.print(
            Panel.fit(
                "[bold blue]OLLIE[/bold blue] - Offline Local Language Intelligence\n"
                f"[dim]Say '{self._wake_phrase}' to wake, or press Ctrl+C to exit[/dim]",
                border_style="blue",
            )
        )
        self.console.print()

        # Greet user
        await self.speak("Hello! I'm OLLIE, your voice assistant. How can I help?")

        self._running = True
        self._wake_detected = False

        while self._running:
            try:
                # Check for wake word using openWakeWord
                if self.wakeword and self.wakeword.model:
                    # Read audio chunk from arecord
                    chunk = self.wakeword._read_audio_chunk()
                    if chunk is not None and self._running:
                        # Process for wake word detection
                        detected = self.wakeword.process_audio(chunk)
                        if detected and self._running:
                            # Wake word detected - listen for command
                            self.console.print("[bold green]Listening...[/bold green]")
                            query = await self.listen(timeout=10.0)
                            if query and self._running:
                                await self.process_query(query)
                else:
                    # Fallback: wait for keyboard input
                    await asyncio.sleep(0.1)

                await asyncio.sleep(0.01)  # Prevent tight loop

            except KeyboardInterrupt:
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")
                await asyncio.sleep(1)

        await self.shutdown()

    async def shutdown(self) -> None:
        """Clean shutdown."""
        self._running = False
        self.console.print("\n[dim]Goodbye![/dim]")
        if self.wakeword:
            await self.wakeword.stop()


async def async_main() -> None:
    """Async entry point."""
    assistant = OllieAssistant()

    # Handle signals - set flag directly for immediate response
    def handle_signal():
        assistant._running = False

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    try:
        await assistant.run()
    finally:
        await assistant.shutdown()


def main() -> None:
    """Entry point."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()

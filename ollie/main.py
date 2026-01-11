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
from .voice.wakeword import WakeWordDetector
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
)


class OllieAssistant:
    """Main voice assistant class."""

    def __init__(self) -> None:
        self.console = Console()
        self.settings = get_settings()
        self.orchestrator = Orchestrator()
        self.tts: Optional[TTS] = None
        self.stt: Optional[STT] = None
        self.wakeword: Optional[WakeWordDetector] = None
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

        # Initialize wake word detector
        self.wakeword = WakeWordDetector(
            wake_word=self.settings.wake_word,
            threshold=self.settings.wake_word_threshold,
            on_wake=self._on_wake,
        )
        self.console.print("[dim]  Wake word: Loading model...[/dim]")
        await self.wakeword.load()
        if self.wakeword.model:
            self.console.print(f"[dim]  Wake word: Listening for '{self.settings.wake_word}'[/dim]")
        else:
            self.console.print("[yellow]  Wake word: Not available (press Enter to speak)[/yellow]")

        # Initialize audio capture
        self.audio = AudioCapture(sample_rate=16000, channels=1)
        await self.audio.start()
        if self.audio.is_running:
            self.console.print("[dim]  Audio: Microphone ready[/dim]")
        else:
            self.console.print("[yellow]  Audio: Microphone not available[/yellow]")

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
        """Speak text using TTS."""
        if self.tts:
            await self.tts.speak(text)

    async def listen(self, timeout: float = 5.0) -> str:
        """Listen for speech and transcribe."""
        if not self.audio or not self.stt:
            return ""

        self.audio.clear()
        start_time = time.time()
        audio_chunks = []
        silence_start = None
        silence_threshold = 1.0  # seconds of silence to stop

        while time.time() - start_time < timeout:
            chunk = self.audio.get_audio(timeout=0.1)
            if chunk is not None:
                audio_chunks.append(chunk)

                # Simple voice activity detection
                volume = np.abs(chunk).mean()
                if volume < 500:  # Silence threshold
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > silence_threshold and len(audio_chunks) > 10:
                        break
                else:
                    silence_start = None

            await asyncio.sleep(0.01)

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
                f"[dim]Say '{self.settings.wake_word}' to wake, or press Ctrl+C to exit[/dim]",
                border_style="blue",
            )
        )
        self.console.print()

        # Greet user
        await self.speak("Hello! I'm OLLIE, your voice assistant. How can I help?")

        self._running = True

        while self._running:
            try:
                # Check for wake word
                if self.wakeword and self.wakeword.model and self.audio:
                    chunk = self.audio.get_audio(timeout=0.1)
                    if chunk is not None:
                        if self.wakeword.process_audio(chunk.flatten()):
                            # Wake word detected
                            await self.speak("Yes?")
                            query = await self.listen(timeout=10.0)
                            if query:
                                await self.process_query(query)
                            self.wakeword.reset()
                else:
                    # Fallback: wait for keyboard input
                    await asyncio.sleep(0.1)

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
        if self.audio:
            await self.audio.stop()


async def async_main() -> None:
    """Async entry point."""
    assistant = OllieAssistant()

    # Handle signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(assistant.shutdown()))

    await assistant.run()


def main() -> None:
    """Entry point."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()

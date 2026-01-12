"""Wake word detection using openWakeWord.

This is much faster and more reliable than Whisper-based detection.
Uses pre-trained models that run efficiently on Raspberry Pi.
"""

import asyncio
import subprocess
from typing import Callable, Optional

import numpy as np


class OpenWakeWordDetector:
    """Detect wake word using openWakeWord library.

    Uses ALSA arecord for audio capture since sounddevice has issues
    with the XVF3800 device detection.
    """

    SAMPLE_RATE = 16000
    CHUNK_SAMPLES = 1280  # 80ms chunks as expected by openWakeWord

    def __init__(
        self,
        wake_word: str = "hey_ollie",
        threshold: float = 0.5,
        on_wake: Optional[Callable[[], None]] = None,
        audio_device: str = "hw:3,0",
        custom_model_path: Optional[str] = None,
    ) -> None:
        self.wake_word = wake_word
        self.threshold = threshold
        self.on_wake = on_wake
        self.audio_device = audio_device
        self.custom_model_path = custom_model_path
        self.model = None
        self._loaded = False
        self._running = False
        self._paused = False
        self._arecord_proc = None

    async def load(self) -> None:
        """Load the openWakeWord model."""
        if self._loaded:
            return

        try:
            from openwakeword.model import Model
            import openwakeword

            loop = asyncio.get_event_loop()

            def _load():
                # Use custom model if provided
                if self.custom_model_path:
                    return Model(wakeword_model_paths=[self.custom_model_path])

                # Find the model path for the requested wake word
                model_paths = openwakeword.get_pretrained_model_paths()
                matching = [p for p in model_paths if self.wake_word in p.lower()]

                if matching:
                    return Model(wakeword_model_paths=[matching[0]])
                else:
                    # Load all default models
                    return Model()

            self.model = await loop.run_in_executor(None, _load)
            self._loaded = True
            print(f"[WakeWord] openWakeWord ready: {list(self.model.models.keys())}")

        except ImportError:
            print("[WakeWord] openwakeword not installed. Install with: pip install openwakeword")
            self.model = None
        except Exception as e:
            print(f"[WakeWord] Failed to load model: {e}")
            self.model = None

    def _start_arecord(self) -> None:
        """Start arecord subprocess for audio capture."""
        if self._arecord_proc is not None:
            return

        self._arecord_proc = subprocess.Popen(
            [
                "arecord",
                "-D", self.audio_device,
                "-f", "S16_LE",
                "-r", str(self.SAMPLE_RATE),
                "-c", "2",  # Stereo from XVF3800
                "-t", "raw",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def _stop_arecord(self) -> None:
        """Stop arecord subprocess."""
        if self._arecord_proc is not None:
            self._arecord_proc.terminate()
            try:
                self._arecord_proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._arecord_proc.kill()
            self._arecord_proc = None

    def _read_audio_chunk(self) -> Optional[np.ndarray]:
        """Read a chunk of audio from arecord."""
        if self._arecord_proc is None:
            return None

        # 16-bit stereo = 4 bytes per sample
        chunk_bytes = self.CHUNK_SAMPLES * 2 * 2
        raw = self._arecord_proc.stdout.read(chunk_bytes)

        if len(raw) < chunk_bytes:
            return None

        # Convert to numpy array (stereo int16)
        audio = np.frombuffer(raw, dtype=np.int16).reshape(-1, 2)

        # Use channel 1 (beamformed output from XVF3800)
        return audio[:, 1]

    def process_audio(self, audio_chunk: np.ndarray) -> bool:
        """Process audio chunk and check for wake word.

        Args:
            audio_chunk: Audio samples (int16, 16kHz, mono)

        Returns:
            True if wake word detected
        """
        if not self._loaded or self.model is None or self._paused:
            return False

        # Run prediction
        prediction = self.model.predict(audio_chunk)

        # Check for detection
        for model_name, score in prediction.items():
            if score > self.threshold:
                print(f"[WakeWord] Detected: {model_name} (score: {score:.3f})")
                if self.on_wake:
                    self.on_wake()
                # Reset model state after detection to avoid repeat triggers
                self.model.reset()
                return True

        return False

    def pause(self) -> None:
        """Pause wake word detection."""
        self._paused = True
        if self.model:
            self.model.reset()

    def resume(self) -> None:
        """Resume wake word detection."""
        if self.model:
            self.model.reset()
        self._paused = False

    def flush_audio_buffer(self) -> None:
        """Flush any buffered audio to avoid processing stale data (like our own speech)."""
        if self._arecord_proc is None:
            return

        # Read and discard all available audio in the pipe buffer
        # This prevents processing our own TTS output as a wake word
        import select
        while True:
            # Check if there's data available without blocking
            readable, _, _ = select.select([self._arecord_proc.stdout], [], [], 0)
            if not readable:
                break
            # Read and discard a chunk
            chunk_bytes = self.CHUNK_SAMPLES * 2 * 2
            data = self._arecord_proc.stdout.read(chunk_bytes)
            if len(data) < chunk_bytes:
                break

    async def start(self) -> None:
        """Start wake word detection loop."""
        if not self._loaded:
            await self.load()

        if self.model is None:
            return

        self._running = True
        self._start_arecord()

    async def stop(self) -> None:
        """Stop wake word detection."""
        self._running = False
        self._stop_arecord()

    async def run_detection_loop(self) -> None:
        """Run the main detection loop."""
        while self._running:
            if self._paused:
                await asyncio.sleep(0.1)
                continue

            chunk = self._read_audio_chunk()
            if chunk is not None:
                self.process_audio(chunk)

            # Small sleep to prevent tight loop
            await asyncio.sleep(0.01)

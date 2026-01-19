"""Wake word detection using Picovoice Porcupine.

Porcupine is a highly accurate, lightweight wake word engine.
Requires an access key from https://console.picovoice.ai/
"""

import asyncio
import subprocess
from typing import Callable, Optional

import numpy as np


class PorcupineWakeWordDetector:
    """Detect wake word using Picovoice Porcupine.

    Uses ALSA arecord for audio capture.
    """

    SAMPLE_RATE = 16000

    def __init__(
        self,
        access_key: str,
        keyword: str = "jarvis",
        sensitivity: float = 0.5,
        on_wake: Optional[Callable[[], None]] = None,
        audio_device: str = "plughw:2,0",
        custom_keyword_path: Optional[str] = None,
    ) -> None:
        """Initialize Porcupine wake word detector.

        Args:
            access_key: Picovoice access key from console.picovoice.ai
            keyword: Built-in keyword name (jarvis, alexa, computer, etc.)
            sensitivity: Detection sensitivity 0.0-1.0 (higher = more sensitive)
            on_wake: Callback when wake word detected
            audio_device: ALSA device for audio capture
            custom_keyword_path: Path to custom .ppn keyword file
        """
        self.access_key = access_key
        self.keyword = keyword
        self.sensitivity = sensitivity
        self.on_wake = on_wake
        self.audio_device = audio_device
        self.custom_keyword_path = custom_keyword_path
        self.porcupine = None
        self._loaded = False
        self._running = False
        self._paused = False
        self._arecord_proc = None

    async def load(self) -> None:
        """Load the Porcupine engine."""
        if self._loaded:
            return

        try:
            import pvporcupine

            loop = asyncio.get_event_loop()

            def _load():
                if self.custom_keyword_path:
                    return pvporcupine.create(
                        access_key=self.access_key,
                        keyword_paths=[self.custom_keyword_path],
                        sensitivities=[self.sensitivity],
                    )
                else:
                    return pvporcupine.create(
                        access_key=self.access_key,
                        keywords=[self.keyword],
                        sensitivities=[self.sensitivity],
                    )

            self.porcupine = await loop.run_in_executor(None, _load)
            self._loaded = True
            print(f"[WakeWord] Porcupine ready: '{self.keyword}' (sensitivity: {self.sensitivity})")

        except pvporcupine.PorcupineActivationError as e:
            print(f"[WakeWord] Porcupine activation failed: {e}")
            print("[WakeWord] Check your access key at https://console.picovoice.ai/")
            self.porcupine = None
        except pvporcupine.PorcupineError as e:
            print(f"[WakeWord] Porcupine error: {e}")
            self.porcupine = None
        except ImportError:
            print("[WakeWord] pvporcupine not installed. Install with: pip install pvporcupine")
            self.porcupine = None
        except Exception as e:
            print(f"[WakeWord] Failed to load Porcupine: {e}")
            self.porcupine = None

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
                "-c", "2",
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
        if self._arecord_proc is None or self.porcupine is None:
            return None

        # Porcupine expects specific frame length
        frame_length = self.porcupine.frame_length
        # 16-bit stereo = 4 bytes per sample
        chunk_bytes = frame_length * 2 * 2
        raw = self._arecord_proc.stdout.read(chunk_bytes)

        if len(raw) < chunk_bytes:
            return None

        # Convert to numpy array (stereo int16)
        audio = np.frombuffer(raw, dtype=np.int16).reshape(-1, 2)

        # Use channel 1 (beamformed output from XVF3800)
        return audio[:, 0]

    def process_audio(self, audio_chunk: np.ndarray) -> bool:
        """Process audio chunk and check for wake word.

        Args:
            audio_chunk: Audio samples (int16, 16kHz, mono)

        Returns:
            True if wake word detected
        """
        if not self._loaded or self.porcupine is None or self._paused:
            return False

        # Run detection
        result = self.porcupine.process(audio_chunk)

        if result >= 0:
            print(f"[WakeWord] Detected: {self.keyword}")
            if self.on_wake:
                self.on_wake()
            return True

        return False

    def pause(self) -> None:
        """Pause wake word detection."""
        self._paused = True

    def resume(self) -> None:
        """Resume wake word detection."""
        self._paused = False

    def flush_audio_buffer(self) -> None:
        """Flush any buffered audio to avoid processing stale data."""
        if self._arecord_proc is None:
            return

        import select
        frame_length = self.porcupine.frame_length if self.porcupine else 512
        chunk_bytes = frame_length * 2 * 2

        while True:
            readable, _, _ = select.select([self._arecord_proc.stdout], [], [], 0)
            if not readable:
                break
            data = self._arecord_proc.stdout.read(chunk_bytes)
            if len(data) < chunk_bytes:
                break

    async def start(self) -> None:
        """Start wake word detection loop."""
        if not self._loaded:
            await self.load()

        if self.porcupine is None:
            return

        self._running = True
        self._start_arecord()

    async def stop(self) -> None:
        """Stop wake word detection."""
        self._running = False
        self._stop_arecord()
        if self.porcupine:
            self.porcupine.delete()
            self.porcupine = None

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
            await asyncio.sleep(0.001)

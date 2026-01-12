"""Wake word detection using Whisper-based transcription."""

import asyncio
from typing import Callable, Optional

import numpy as np

from ..core.config import get_settings


class WakeWordDetector:
    """Detect wake word using Whisper transcription.

    This approach accumulates audio in a rolling buffer and periodically
    transcribes it to check for the wake word. Less efficient than dedicated
    wake word models but works without additional dependencies.
    """

    # Audio buffer settings
    SAMPLE_RATE = 16000
    BUFFER_SECONDS = 2.0  # Rolling buffer size
    CHECK_INTERVAL_SECONDS = 1.0  # How often to check for wake word (1s reduces CPU load)

    def __init__(
        self,
        wake_word: str = "ollie",
        threshold: float = 0.5,  # Not used for Whisper approach
        on_wake: Optional[Callable[[], None]] = None,
    ) -> None:
        self.settings = get_settings()
        self.wake_word = wake_word.lower()
        self.threshold = threshold
        self.on_wake = on_wake
        self.model = None
        self._loaded = False
        self._running = False
        self._paused = False  # For muting during TTS

        # Audio buffer
        self._buffer_size = int(self.SAMPLE_RATE * self.BUFFER_SECONDS)
        self._audio_buffer = np.zeros(self._buffer_size, dtype=np.float32)
        self._buffer_pos = 0
        self._samples_since_check = 0
        self._check_interval_samples = int(self.SAMPLE_RATE * self.CHECK_INTERVAL_SECONDS)

        # Variations of wake word to match
        self._wake_variants = self._generate_variants(wake_word)

    def _generate_variants(self, wake_word: str) -> set[str]:
        """Generate common transcription variants of the wake word."""
        word = wake_word.lower()
        variants = {word}

        # Common Whisper transcription variations for "ollie"
        # Whisper often hears "ollie" as "holy" or "molly" - verified on device
        if word == "ollie":
            variants.update([
                "ollie", "olly", "olli",
                "holy",  # Whisper commonly transcribes "ollie" as "holy"
                "molly", "mollie",  # Another common Whisper interpretation
                "hey ollie", "hey olly", "hey holy", "hey molly",
                "ok ollie", "okay ollie",
            ])

        return variants

    async def load(self) -> None:
        """Load the Whisper model for wake word detection."""
        if self._loaded:
            return

        try:
            from faster_whisper import WhisperModel

            loop = asyncio.get_event_loop()

            # Use tiny model for wake word - faster response
            self.model = await loop.run_in_executor(
                None,
                lambda: WhisperModel(
                    "tiny",  # Smallest/fastest for wake word
                    device="cpu",
                    compute_type="int8",
                ),
            )
            self._loaded = True
            print(f"[WakeWord] Whisper-based detection ready for '{self.wake_word}'")

        except ImportError:
            print("[WakeWord] faster-whisper not installed. Install with: pip install faster-whisper")
            self.model = None
        except Exception as e:
            print(f"[WakeWord] Failed to load model: {e}")
            self.model = None

    def _add_to_buffer(self, audio_chunk: np.ndarray) -> None:
        """Add audio to the rolling buffer without checking for wake word.

        Args:
            audio_chunk: Audio samples (int16 or float32, 16kHz, mono)
        """
        # Convert to float32 if needed
        if audio_chunk.dtype == np.int16:
            audio_float = audio_chunk.astype(np.float32) / 32768.0
        else:
            audio_float = audio_chunk.astype(np.float32)

        # Flatten if needed
        audio_float = audio_float.flatten()

        # Add to rolling buffer
        chunk_len = len(audio_float)
        if chunk_len >= self._buffer_size:
            # Chunk larger than buffer - just use the end
            self._audio_buffer[:] = audio_float[-self._buffer_size:]
            self._buffer_pos = 0
        else:
            # Add chunk to circular buffer
            end_pos = self._buffer_pos + chunk_len
            if end_pos <= self._buffer_size:
                self._audio_buffer[self._buffer_pos:end_pos] = audio_float
            else:
                # Wrap around
                first_part = self._buffer_size - self._buffer_pos
                self._audio_buffer[self._buffer_pos:] = audio_float[:first_part]
                self._audio_buffer[:chunk_len - first_part] = audio_float[first_part:]
            self._buffer_pos = end_pos % self._buffer_size

        self._samples_since_check += chunk_len

    def _should_check(self) -> bool:
        """Check if enough samples have accumulated to run detection."""
        if self._paused:
            return False
        if self._samples_since_check >= self._check_interval_samples:
            self._samples_since_check = 0
            return True
        return False

    def pause(self) -> None:
        """Pause wake word detection (e.g., during TTS playback)."""
        self._paused = True
        # Clear the buffer to avoid detecting echoed speech
        self._audio_buffer.fill(0)
        self._buffer_pos = 0
        self._samples_since_check = 0

    def resume(self) -> None:
        """Resume wake word detection."""
        # Clear buffer again when resuming
        self._audio_buffer.fill(0)
        self._buffer_pos = 0
        self._samples_since_check = 0
        self._paused = False

    def process_audio(self, audio_chunk: np.ndarray) -> bool:
        """Process audio chunk and check for wake word.

        Args:
            audio_chunk: Audio samples (int16 or float32, 16kHz, mono)

        Returns:
            True if wake word detected
        """
        if self.model is None:
            return False

        self._add_to_buffer(audio_chunk)

        if not self._should_check():
            return False

        # Run wake word detection (synchronous)
        return self._check_wake_word()

    def _check_wake_word(self) -> bool:
        """Check buffer for wake word using Whisper."""
        try:
            # Get audio from circular buffer in correct order
            if self._buffer_pos == 0:
                audio = self._audio_buffer.copy()
            else:
                audio = np.concatenate([
                    self._audio_buffer[self._buffer_pos:],
                    self._audio_buffer[:self._buffer_pos]
                ])

            # Check if there's meaningful audio (not just silence)
            if np.abs(audio).max() < 0.01:
                return False

            # Transcribe - disable VAD filter for XVF3800 beamformed audio
            # The beamformed output is already cleaned up, VAD is too aggressive
            segments, info = self.model.transcribe(
                audio,
                beam_size=1,
                language="en",
                vad_filter=False,
                without_timestamps=True,
            )

            text = " ".join(seg.text for seg in segments).lower().strip()

            if not text:
                return False

            # Check for wake word variants
            for variant in self._wake_variants:
                if variant in text:
                    print(f"[WakeWord] Detected: '{text}'")
                    if self.on_wake:
                        self.on_wake()
                    return True

            return False

        except Exception as e:
            print(f"[WakeWord] Detection error: {e}")
            return False

    async def check_wake_word_async(self) -> bool:
        """Async version of wake word check."""
        if self.model is None:
            return False

        if not self._should_check():
            return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._check_wake_word)

    def reset(self) -> None:
        """Reset the detector state."""
        self._audio_buffer.fill(0)
        self._buffer_pos = 0
        self._samples_since_check = 0

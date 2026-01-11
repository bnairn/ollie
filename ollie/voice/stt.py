"""Speech-to-Text using faster-whisper."""

import asyncio
from pathlib import Path
from typing import Optional

import numpy as np

from ..core.config import get_settings


class STT:
    """Speech-to-text using faster-whisper."""

    def __init__(self, model_size: str = "base") -> None:
        self.settings = get_settings()
        self.model_size = model_size
        self.model = None
        self._loaded = False

    async def load(self) -> None:
        """Load the whisper model."""
        if self._loaded:
            return

        try:
            # Import here to avoid slow startup if not using voice
            from faster_whisper import WhisperModel

            # Run model loading in executor to not block
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None,
                lambda: WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="int8",
                ),
            )
            self._loaded = True
        except ImportError:
            print("[STT] faster-whisper not installed. Install with: pip install faster-whisper")
            self.model = None
        except Exception as e:
            print(f"[STT] Failed to load model: {e}")
            self.model = None

    async def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe audio to text.

        Args:
            audio: Audio samples as numpy array (float32, mono)
            sample_rate: Sample rate of audio (default 16000)

        Returns:
            Transcribed text
        """
        if not self._loaded:
            await self.load()

        if self.model is None:
            return ""

        try:
            loop = asyncio.get_event_loop()

            def _transcribe():
                segments, info = self.model.transcribe(
                    audio,
                    beam_size=5,
                    language="en",
                    vad_filter=True,
                )
                return " ".join(segment.text.strip() for segment in segments)

            text = await loop.run_in_executor(None, _transcribe)
            return text.strip()

        except Exception as e:
            print(f"[STT] Transcription error: {e}")
            return ""

    async def transcribe_file(self, audio_path: Path) -> str:
        """Transcribe audio file to text."""
        if not self._loaded:
            await self.load()

        if self.model is None:
            return ""

        try:
            loop = asyncio.get_event_loop()

            def _transcribe():
                segments, info = self.model.transcribe(
                    str(audio_path),
                    beam_size=5,
                    language="en",
                    vad_filter=True,
                )
                return " ".join(segment.text.strip() for segment in segments)

            text = await loop.run_in_executor(None, _transcribe)
            return text.strip()

        except Exception as e:
            print(f"[STT] Transcription error: {e}")
            return ""

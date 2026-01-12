"""Speech-to-Text with support for local Whisper and cloud Deepgram."""

import asyncio
import io
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from ..core.config import get_settings


class STT:
    """Speech-to-text with local Whisper and optional cloud Deepgram."""

    def __init__(self, model_size: str = "base") -> None:
        self.settings = get_settings()
        self.model_size = model_size
        self.model = None
        self._loaded = False
        self._use_deepgram = False
        self._deepgram_client = None

    async def load(self) -> None:
        """Load the STT backend (Deepgram if available, otherwise Whisper)."""
        if self._loaded:
            return

        # Try Deepgram first if API key is configured
        deepgram_key = getattr(self.settings, "deepgram_api_key", "")
        if deepgram_key:
            try:
                from deepgram import DeepgramClient

                self._deepgram_client = DeepgramClient(api_key=deepgram_key)
                self._use_deepgram = True
                self._loaded = True
                self.model = True  # Flag that we have a working backend
                print("[STT] Deepgram ready (cloud)")
                return
            except ImportError:
                print("[STT] deepgram-sdk not installed, falling back to Whisper")
            except Exception as e:
                print(f"[STT] Deepgram init failed: {e}, falling back to Whisper")

        # Fall back to local Whisper
        try:
            from faster_whisper import WhisperModel

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
            self._use_deepgram = False
            print(f"[STT] Whisper ready (local, {self.model_size})")
        except ImportError:
            print("[STT] faster-whisper not installed. Install with: pip install faster-whisper")
            self.model = None
        except Exception as e:
            print(f"[STT] Failed to load Whisper: {e}")
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

        if self._use_deepgram:
            return await self._transcribe_deepgram(audio, sample_rate)
        else:
            return await self._transcribe_whisper(audio, sample_rate)

    async def _transcribe_deepgram(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcribe using Deepgram cloud API (SDK v5)."""
        try:
            # Convert float32 audio to int16 WAV bytes
            audio_int16 = (audio * 32767).astype(np.int16)
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_int16.tobytes())

            wav_bytes = wav_buffer.getvalue()

            # Run in executor to not block
            loop = asyncio.get_event_loop()

            def _call_deepgram():
                # SDK v5 API: client.listen.v1.media.transcribe_file()
                response = self._deepgram_client.listen.v1.media.transcribe_file(
                    request=wav_bytes,
                    model="nova-2",
                    language="en",
                    smart_format=True,
                )
                return response

            response = await loop.run_in_executor(None, _call_deepgram)

            # Extract transcript
            transcript = (
                response.results.channels[0].alternatives[0].transcript
                if response.results.channels
                else ""
            )
            return transcript.strip()

        except Exception as e:
            print(f"[STT] Deepgram error: {e}")
            # Fall back to Whisper if Deepgram fails
            if self.model and not isinstance(self.model, bool):
                print("[STT] Falling back to Whisper")
                return await self._transcribe_whisper(audio, sample_rate)
            return ""

    async def _transcribe_whisper(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcribe using local Whisper."""
        try:
            loop = asyncio.get_event_loop()

            def _transcribe():
                # Optimized for speed on Raspberry Pi:
                # - beam_size=1 for fastest decoding
                # - Disable VAD filter - XVF3800 beamformed output is already processed
                segments, info = self.model.transcribe(
                    audio,
                    beam_size=1,
                    language="en",
                    vad_filter=False,
                )
                return " ".join(segment.text.strip() for segment in segments)

            text = await loop.run_in_executor(None, _transcribe)
            return text.strip()

        except Exception as e:
            print(f"[STT] Whisper error: {e}")
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
                    beam_size=1,
                    language="en",
                    vad_filter=False,
                )
                return " ".join(segment.text.strip() for segment in segments)

            text = await loop.run_in_executor(None, _transcribe)
            return text.strip()

        except Exception as e:
            print(f"[STT] Transcription error: {e}")
            return ""

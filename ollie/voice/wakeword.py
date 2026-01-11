"""Wake word detection using openWakeWord."""

import asyncio
from typing import Callable, Optional

import numpy as np

from ..core.config import get_settings


class WakeWordDetector:
    """Detect wake word 'ollie' using openWakeWord."""

    def __init__(
        self,
        wake_word: str = "ollie",
        threshold: float = 0.5,
        on_wake: Optional[Callable[[], None]] = None,
    ) -> None:
        self.settings = get_settings()
        self.wake_word = wake_word.lower()
        self.threshold = threshold
        self.on_wake = on_wake
        self.model = None
        self._loaded = False
        self._running = False

    async def load(self) -> None:
        """Load the wake word model."""
        if self._loaded:
            return

        try:
            from openwakeword.model import Model

            loop = asyncio.get_event_loop()

            # openWakeWord has pre-trained models including "hey_jarvis"
            # We'll use a similar approach - for custom "ollie" we'd need to train
            # For now, use the generic model that can detect various wake words
            self.model = await loop.run_in_executor(
                None,
                lambda: Model(
                    wakeword_models=["hey_jarvis"],  # Placeholder - replace with ollie model
                    inference_framework="onnx",
                ),
            )
            self._loaded = True

        except ImportError:
            print("[WakeWord] openwakeword not installed. Install with: pip install openwakeword")
            self.model = None
        except Exception as e:
            print(f"[WakeWord] Failed to load model: {e}")
            self.model = None

    def process_audio(self, audio_chunk: np.ndarray) -> bool:
        """Process audio chunk and check for wake word.

        Args:
            audio_chunk: Audio samples (int16, 16kHz, mono)

        Returns:
            True if wake word detected
        """
        if self.model is None:
            return False

        try:
            # openWakeWord expects int16 audio
            prediction = self.model.predict(audio_chunk)

            # Check if any model detected wake word above threshold
            for model_name, score in prediction.items():
                if score > self.threshold:
                    if self.on_wake:
                        self.on_wake()
                    return True

            return False

        except Exception as e:
            print(f"[WakeWord] Detection error: {e}")
            return False

    def reset(self) -> None:
        """Reset the detector state."""
        if self.model:
            self.model.reset()

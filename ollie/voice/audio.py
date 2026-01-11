"""Audio capture and playback utilities."""

import asyncio
import queue
from typing import Optional, Callable

import numpy as np


class AudioCapture:
    """Capture audio from microphone using sounddevice."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
        device: Optional[int] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.device = device
        self._stream = None
        self._running = False
        self._audio_queue: queue.Queue = queue.Queue()

    def _audio_callback(self, indata, frames, time, status):
        """Callback for audio stream."""
        if status:
            print(f"[Audio] {status}")
        # Copy the data to avoid issues with the buffer
        self._audio_queue.put(indata.copy())

    async def start(self) -> None:
        """Start audio capture."""
        if self._running:
            return

        try:
            import sounddevice as sd

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.int16,
                blocksize=self.chunk_size,
                device=self.device,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._running = True
        except ImportError:
            print("[Audio] sounddevice not installed. Install with: pip install sounddevice")
        except Exception as e:
            print(f"[Audio] Failed to start capture: {e}")

    async def stop(self) -> None:
        """Stop audio capture."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._running = False

    def get_audio(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """Get audio chunk from queue."""
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_all_audio(self) -> np.ndarray:
        """Get all available audio from queue."""
        chunks = []
        while True:
            try:
                chunk = self._audio_queue.get_nowait()
                chunks.append(chunk)
            except queue.Empty:
                break

        if chunks:
            return np.concatenate(chunks, axis=0)
        return np.array([], dtype=np.int16)

    def clear(self) -> None:
        """Clear the audio queue."""
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    @property
    def is_running(self) -> bool:
        return self._running


def list_audio_devices() -> None:
    """List available audio devices."""
    try:
        import sounddevice as sd
        print(sd.query_devices())
    except ImportError:
        print("sounddevice not installed")

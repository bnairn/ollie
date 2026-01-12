"""Audio capture and playback utilities."""

import asyncio
import queue
from typing import Optional, Union

import numpy as np


def find_device_by_name(name: str, kind: str = "input") -> Optional[int]:
    """Find audio device ID by name substring.

    Args:
        name: Substring to search for in device name
        kind: 'input' or 'output'

    Returns:
        Device ID or None if not found
    """
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if name.lower() in dev["name"].lower():
                if kind == "input" and dev["max_input_channels"] > 0:
                    return i
                elif kind == "output" and dev["max_output_channels"] > 0:
                    return i
        return None
    except Exception:
        return None


class AudioCapture:
    """Capture audio from microphone using sounddevice."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
        device: Optional[Union[int, str]] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels  # Output channels (after conversion)
        self.chunk_size = chunk_size
        self._device_spec = device  # Can be int, string name, or None
        self.device = None  # Resolved device ID
        self._stream = None
        self._running = False
        self._audio_queue: queue.Queue = queue.Queue()
        self._input_channels = channels  # Actual input channels from device

    def _audio_callback(self, indata, frames, time, status):
        """Callback for audio stream."""
        if status:
            print(f"[Audio] {status}")

        # Convert stereo to mono if needed
        if self._input_channels == 2 and self.channels == 1:
            # XVF3800: Channel 1 has beamformed audio, Channel 0 is reference
            # Use only Channel 1 for best speech recognition
            mono = indata[:, 1].astype(indata.dtype)
            self._audio_queue.put(mono.copy())
        else:
            self._audio_queue.put(indata.copy())

    async def start(self) -> None:
        """Start audio capture."""
        if self._running:
            return

        try:
            import sounddevice as sd

            # Resolve device specification
            if isinstance(self._device_spec, str):
                self.device = find_device_by_name(self._device_spec, "input")
                if self.device is None:
                    print(f"[Audio] Device '{self._device_spec}' not found, using default")
            elif isinstance(self._device_spec, int):
                self.device = self._device_spec

            # Query device to get actual channel count
            if self.device is not None:
                dev_info = sd.query_devices(self.device)
                max_channels = dev_info.get("max_input_channels", 1)
                # Some devices (like XVF3800) only support stereo
                if self.channels == 1 and max_channels >= 2:
                    self._input_channels = 2
                    print(f"[Audio] Device requires stereo, will convert to mono")
                else:
                    self._input_channels = self.channels

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self._input_channels,
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

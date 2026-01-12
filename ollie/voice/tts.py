"""Text-to-Speech using Piper."""

import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ..core.config import get_settings


class TTS:
    """Text-to-speech using Piper."""

    def __init__(self, model_path: Optional[Path] = None) -> None:
        self.settings = get_settings()
        self.model_path = model_path or self.settings.piper_model_path
        self._check_piper()

    def _check_piper(self) -> None:
        """Check if piper is available (as Python module or binary)."""
        # Check common locations for piper binary
        piper_paths = [
            "piper",  # In PATH
            str(Path.home() / ".local" / "bin" / "piper"),  # User local install
            str(Path.home() / "ollie" / "venv" / "bin" / "piper"),  # Old venv install
            "/usr/local/bin/piper",
            "/usr/bin/piper",
        ]

        for piper_path in piper_paths:
            try:
                result = subprocess.run(
                    [piper_path, "--help"],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    self.piper_available = True
                    self.piper_cmd = [piper_path]
                    return
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        # Try Python module as fallback
        try:
            result = subprocess.run(
                ["python", "-m", "piper", "--help"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                self.piper_available = True
                self.piper_cmd = ["python", "-m", "piper"]
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        self.piper_available = False
        self.piper_cmd = []

    async def speak(self, text: str) -> bool:
        """Speak text using Piper TTS.

        Returns True if speech was successful.
        """
        if not text.strip():
            return True

        if not self.piper_available:
            print(f"[TTS unavailable] {text}")
            return False

        try:
            # Use temp file approach since raw piping has issues with pw-play
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = Path(f.name)

            # Generate WAV file
            cmd = self.piper_cmd + ["--output_file", str(temp_path)]

            if self.model_path and self.model_path.exists():
                cmd.extend(["--model", str(self.model_path)])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await proc.communicate(text.encode())

            if proc.returncode != 0:
                temp_path.unlink(missing_ok=True)
                return False

            # Play the WAV file
            play_proc = await asyncio.create_subprocess_exec(
                "pw-play", str(temp_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await play_proc.wait()

            # Clean up
            temp_path.unlink(missing_ok=True)

            return play_proc.returncode == 0

        except Exception as e:
            print(f"[TTS error] {e}")
            return False

    async def speak_file(self, text: str, output_path: Path) -> bool:
        """Generate speech to a WAV file."""
        if not text.strip():
            return True

        if not self.piper_available:
            return False

        try:
            cmd = ["piper", "--output_file", str(output_path)]

            if self.model_path and self.model_path.exists():
                cmd.extend(["--model", str(self.model_path)])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate(text.encode())
            return proc.returncode == 0

        except Exception as e:
            print(f"[TTS error] {e}")
            return False

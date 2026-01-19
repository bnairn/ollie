"""Volume control skill - adjust system audio volume."""

import asyncio
import re
from typing import Any

from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class VolumeSkill(Skill):
    """Control system audio volume."""

    name = "volume"
    description = "Adjust system audio volume"
    examples = [
        "Volume up",
        "Volume down",
        "Set volume to 5",
        "Volume to 7",
        "Mute",
        "Unmute",
    ]

    # Volume scale: 0-10 maps to 0-100% (in 10% increments)
    VOLUME_STEP = 10  # 10% per step

    MATCH_PATTERNS = [
        # Volume up/down
        r"(?:turn\s+)?(?:the\s+)?volume\s+(up|down)(?:\s+a\s+(?:bit|little))?",
        r"(?:turn\s+)?(?:it\s+)?(up|down)(?:\s+a\s+(?:bit|little))?",
        r"(louder|quieter)",
        r"(increase|decrease|raise|lower)\s+(?:the\s+)?volume",
        # Set to specific level (0-10)
        r"(?:set\s+)?(?:the\s+)?volume\s+(?:to|at)\s+(\d+)",
        r"volume\s+(\d+)",
        # Mute/unmute
        r"(mute|unmute)",
        r"(?:turn\s+)?(?:the\s+)?sound\s+(off|on)",
    ]

    async def match(self, query: str) -> SkillMatch:
        """Check if user wants to control volume."""
        query_lower = query.lower().strip()

        # Check for volume up/down
        for pattern in self.MATCH_PATTERNS[:4]:
            if match := re.search(pattern, query_lower):
                action = match.group(1).lower()
                if action in ("up", "louder", "increase", "raise"):
                    return self._match(SkillConfidence.HIGH, action="up")
                else:
                    return self._match(SkillConfidence.HIGH, action="down")

        # Check for specific volume level
        for pattern in self.MATCH_PATTERNS[4:6]:
            if match := re.search(pattern, query_lower):
                level = int(match.group(1))
                if 0 <= level <= 10:
                    return self._match(SkillConfidence.HIGH, action="set", level=level)
                else:
                    return self._match(
                        SkillConfidence.HIGH, action="invalid", level=level
                    )

        # Check for mute/unmute
        for pattern in self.MATCH_PATTERNS[6:]:
            if match := re.search(pattern, query_lower):
                action = match.group(1).lower()
                if action in ("mute", "off"):
                    return self._match(SkillConfidence.HIGH, action="mute")
                else:
                    return self._match(SkillConfidence.HIGH, action="unmute")

        return self._no_match()

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Execute volume control."""
        action = extracted.get("action")

        if action == "invalid":
            level = extracted.get("level", 0)
            return SkillResult.error(
                f"Volume level {level} is out of range. Please use 0 to 10."
            )

        if action == "up":
            return await self._volume_up()
        elif action == "down":
            return await self._volume_down()
        elif action == "set":
            level = extracted.get("level", 5)
            return await self._set_volume(level)
        elif action == "mute":
            return await self._mute()
        elif action == "unmute":
            return await self._unmute()
        else:
            return SkillResult.error("I didn't understand that volume command.")

    async def _run_wpctl(self, *args: str) -> tuple[bool, str]:
        """Run wpctl command and return (success, output)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "wpctl",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            success = proc.returncode == 0
            output = stdout.decode().strip() or stderr.decode().strip()
            return success, output
        except FileNotFoundError:
            return False, "wpctl not found - PipeWire may not be installed"
        except Exception as e:
            return False, str(e)

    async def _get_current_volume(self) -> int | None:
        """Get current volume percentage (0-100)."""
        success, output = await self._run_wpctl("get-volume", "@DEFAULT_AUDIO_SINK@")
        if success and output:
            # Output format: "Volume: 0.50" or "Volume: 0.50 [MUTED]"
            if match := re.search(r"Volume:\s*([\d.]+)", output):
                return int(float(match.group(1)) * 100)
        return None

    async def _volume_up(self) -> SkillResult:
        """Increase volume by one step."""
        success, _ = await self._run_wpctl(
            "set-volume", "@DEFAULT_AUDIO_SINK@", f"{self.VOLUME_STEP}%+"
        )

        if success:
            current = await self._get_current_volume()
            if current is not None:
                level = min(10, round(current / 10))
                return SkillResult(
                    success=True,
                    response=f"Volume increased to {level}.",
                    speak=f"Volume {level}.",
                    data={"level": level, "percent": current},
                )
            return SkillResult(
                success=True,
                response="Volume increased.",
                speak="Volume up.",
            )

        return SkillResult.error("Couldn't adjust volume.")

    async def _volume_down(self) -> SkillResult:
        """Decrease volume by one step."""
        success, _ = await self._run_wpctl(
            "set-volume", "@DEFAULT_AUDIO_SINK@", f"{self.VOLUME_STEP}%-"
        )

        if success:
            current = await self._get_current_volume()
            if current is not None:
                level = max(0, round(current / 10))
                return SkillResult(
                    success=True,
                    response=f"Volume decreased to {level}.",
                    speak=f"Volume {level}.",
                    data={"level": level, "percent": current},
                )
            return SkillResult(
                success=True,
                response="Volume decreased.",
                speak="Volume down.",
            )

        return SkillResult.error("Couldn't adjust volume.")

    async def _set_volume(self, level: int) -> SkillResult:
        """Set volume to specific level (0-10)."""
        percent = level * 10
        success, _ = await self._run_wpctl(
            "set-volume", "@DEFAULT_AUDIO_SINK@", f"{percent}%"
        )

        if success:
            if level == 0:
                return SkillResult(
                    success=True,
                    response="Volume set to 0. Audio is now silent.",
                    speak="Volume muted.",
                    data={"level": level, "percent": percent},
                )
            return SkillResult(
                success=True,
                response=f"Volume set to {level}.",
                speak=f"Volume {level}.",
                data={"level": level, "percent": percent},
            )

        return SkillResult.error("Couldn't set volume.")

    async def _mute(self) -> SkillResult:
        """Mute audio."""
        success, _ = await self._run_wpctl("set-mute", "@DEFAULT_AUDIO_SINK@", "1")

        if success:
            return SkillResult(
                success=True,
                response="Audio muted.",
                speak="Muted.",
                data={"muted": True},
            )

        return SkillResult.error("Couldn't mute audio.")

    async def _unmute(self) -> SkillResult:
        """Unmute audio."""
        success, _ = await self._run_wpctl("set-mute", "@DEFAULT_AUDIO_SINK@", "0")

        if success:
            current = await self._get_current_volume()
            if current is not None:
                level = round(current / 10)
                return SkillResult(
                    success=True,
                    response=f"Audio unmuted. Volume is at {level}.",
                    speak=f"Unmuted. Volume {level}.",
                    data={"muted": False, "level": level},
                )
            return SkillResult(
                success=True,
                response="Audio unmuted.",
                speak="Unmuted.",
                data={"muted": False},
            )

        return SkillResult.error("Couldn't unmute audio.")

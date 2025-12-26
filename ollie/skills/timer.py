"""Timer skill - set, list, and cancel timers."""

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


@dataclass
class Timer:
    """A running timer."""

    id: int
    name: str
    duration_seconds: int
    end_time: datetime
    task: asyncio.Task | None = None


class TimerSkill(Skill):
    """Manage timers - set, list, and cancel."""

    name = "timer"
    description = "Set, list, and cancel timers"
    examples = [
        "Set a timer for 5 minutes",
        "Set a 30 second timer",
        "Timer for 1 hour",
        "Cancel the timer",
        "What timers are running?",
    ]

    # Patterns for matching timer requests
    SET_PATTERNS = [
        r"(?:set|start|create)\s+(?:a\s+)?timer\s+(?:for\s+)?(.+)",
        r"timer\s+(?:for\s+)?(.+)",
        r"(?:set|start)\s+(?:a\s+)?(\d+)\s*(second|minute|hour)",
        r"(\d+)\s*(second|minute|hour)\s*timer",
    ]

    LIST_PATTERNS = [
        r"(?:what|which|list|show)\s+timers?",
        r"timers?\s+(?:running|active|left)",
        r"how\s+(?:much|long)\s+(?:time\s+)?(?:left|remaining)",
    ]

    CANCEL_PATTERNS = [
        r"(?:cancel|stop|delete|remove)\s+(?:the\s+)?timer",
        r"(?:cancel|stop|delete|remove)\s+(?:all\s+)?timers?",
    ]

    def __init__(self, on_timer_complete: Callable[[Timer], None] | None = None) -> None:
        self.timers: dict[int, Timer] = {}
        self.next_id = 1
        self.on_timer_complete = on_timer_complete

    async def match(self, query: str) -> SkillMatch:
        """Check if this is a timer-related query."""
        query_lower = query.lower()

        # Check for set timer
        for pattern in self.SET_PATTERNS:
            if match := re.search(pattern, query_lower):
                duration = self._parse_duration(match.group(0))
                if duration:
                    return self._match(
                        SkillConfidence.HIGH,
                        action="set",
                        duration_seconds=duration,
                    )

        # Check for list timers
        for pattern in self.LIST_PATTERNS:
            if re.search(pattern, query_lower):
                return self._match(SkillConfidence.HIGH, action="list")

        # Check for cancel
        for pattern in self.CANCEL_PATTERNS:
            if re.search(pattern, query_lower):
                return self._match(SkillConfidence.HIGH, action="cancel")

        # Weak match if "timer" is mentioned
        if "timer" in query_lower:
            return self._match(SkillConfidence.LOW, action="unknown")

        return self._no_match()

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Execute the timer action."""
        action = extracted.get("action", "unknown")

        if action == "set":
            return await self._set_timer(extracted["duration_seconds"], query)
        elif action == "list":
            return self._list_timers()
        elif action == "cancel":
            return self._cancel_timers()
        else:
            return SkillResult.error(
                "I can set a timer, list active timers, or cancel timers. What would you like?"
            )

    async def _set_timer(self, duration_seconds: int, query: str) -> SkillResult:
        """Set a new timer."""
        timer_id = self.next_id
        self.next_id += 1

        # Extract name from query or use default
        name = self._extract_timer_name(query) or f"Timer {timer_id}"
        end_time = datetime.now() + timedelta(seconds=duration_seconds)

        timer = Timer(
            id=timer_id,
            name=name,
            duration_seconds=duration_seconds,
            end_time=end_time,
        )

        # Create the async task for the timer
        timer.task = asyncio.create_task(self._timer_countdown(timer))
        self.timers[timer_id] = timer

        duration_str = self._format_duration(duration_seconds)
        return SkillResult.ok(
            f"Timer set for {duration_str}.",
            timer_id=timer_id,
            duration=duration_str,
        )

    async def _timer_countdown(self, timer: Timer) -> None:
        """Wait for timer to complete."""
        await asyncio.sleep(timer.duration_seconds)

        if timer.id in self.timers:
            del self.timers[timer.id]
            if self.on_timer_complete:
                self.on_timer_complete(timer)

    def _list_timers(self) -> SkillResult:
        """List all active timers."""
        if not self.timers:
            return SkillResult.ok("No timers are running.")

        lines = ["Active timers:"]
        now = datetime.now()
        for timer in self.timers.values():
            remaining = (timer.end_time - now).total_seconds()
            if remaining > 0:
                remaining_str = self._format_duration(int(remaining))
                lines.append(f"  • {timer.name}: {remaining_str} remaining")

        return SkillResult.ok("\n".join(lines), count=len(self.timers))

    def _cancel_timers(self) -> SkillResult:
        """Cancel all timers."""
        count = len(self.timers)
        if count == 0:
            return SkillResult.ok("No timers to cancel.")

        for timer in self.timers.values():
            if timer.task:
                timer.task.cancel()
        self.timers.clear()

        return SkillResult.ok(
            f"Cancelled {count} timer{'s' if count > 1 else ''}.",
            cancelled=count,
        )

    def _parse_duration(self, text: str) -> int | None:
        """Parse a duration string into seconds."""
        text = text.lower()
        total_seconds = 0

        # Match patterns like "5 minutes", "1 hour 30 minutes", "90 seconds"
        patterns = [
            (r"(\d+)\s*(?:hour|hr)s?", 3600),
            (r"(\d+)\s*(?:minute|min)s?", 60),
            (r"(\d+)\s*(?:second|sec)s?", 1),
        ]

        for pattern, multiplier in patterns:
            for match in re.finditer(pattern, text):
                total_seconds += int(match.group(1)) * multiplier

        return total_seconds if total_seconds > 0 else None

    def _format_duration(self, seconds: int) -> str:
        """Format seconds into a human-readable string."""
        if seconds < 60:
            return f"{seconds} second{'s' if seconds != 1 else ''}"

        minutes, secs = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)

        parts = []
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if secs and not hours:  # Only show seconds if less than an hour
            parts.append(f"{secs} second{'s' if secs != 1 else ''}")

        return " ".join(parts)

    def _extract_timer_name(self, query: str) -> str | None:
        """Try to extract a custom name for the timer."""
        # Look for patterns like "set a pizza timer" or "timer called eggs"
        patterns = [
            r"(?:called|named)\s+(\w+)",
            r"(\w+)\s+timer",
        ]
        for pattern in patterns:
            if match := re.search(pattern, query.lower()):
                name = match.group(1)
                # Filter out common non-name words
                if name not in {"a", "the", "set", "start", "for", "minute", "second", "hour"}:
                    return name.title()
        return None

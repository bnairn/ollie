"""Claude skill - fallback for general questions using Claude API."""

from datetime import datetime
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class ClaudeSkill(Skill):
    """Answer general questions using Claude API."""

    name = "claude"
    description = "Answer general questions using Claude AI"
    examples = [
        "What is the capital of France?",
        "Explain photosynthesis",
        "Who wrote Romeo and Juliet?",
        "What's the difference between a llama and an alpaca?",
    ]

    # Base system prompt for OLLIE persona
    SYSTEM_PROMPT_BASE = """You are OLLIE (Offline Local Language Intelligence), a helpful voice assistant.
Keep responses concise and conversational - aim for 1-3 sentences when possible.
You're running on a Raspberry Pi in someone's home, so be friendly and casual.
If asked about yourself, you can mention you're a privacy-focused assistant.
Don't use markdown formatting in responses since they will be spoken aloud."""

    def _get_system_prompt(self) -> str:
        """Build system prompt with current date/time context."""
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%I:%M %p")
        return f"{self.SYSTEM_PROMPT_BASE}\n\nCurrent date and time: {date_str} at {time_str}."

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=30.0)

    async def match(self, query: str) -> SkillMatch:
        """
        This is a fallback skill - it matches everything with LOW confidence.
        Other skills with higher confidence will take precedence.
        """
        if not query.strip():
            return self._no_match()

        # Always match with LOW confidence as a fallback
        return self._match(SkillConfidence.LOW)

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Send query to Claude API and return response."""
        if not self.settings.anthropic_api_key:
            return SkillResult.error(
                "Claude isn't configured. Add ANTHROPIC_API_KEY to your .env file."
            )

        try:
            response = await self.client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-3-5-haiku-latest",
                    "max_tokens": 300,
                    "system": self._get_system_prompt(),
                    "messages": [{"role": "user", "content": query}],
                },
            )
            response.raise_for_status()
            data = response.json()

            # Extract the text response
            content = data.get("content", [])
            if content and content[0].get("type") == "text":
                answer = content[0].get("text", "")
                return SkillResult(
                    success=True,
                    response=answer,
                    speak=answer,
                    data={
                        "model": data.get("model"),
                        "usage": data.get("usage"),
                    },
                )

            return SkillResult.error("Received unexpected response format from Claude.")

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return SkillResult.error(
                    "Claude API key is invalid. Check your ANTHROPIC_API_KEY."
                )
            if e.response.status_code == 429:
                return SkillResult.error(
                    "Claude API rate limit exceeded. Try again in a moment."
                )
            return SkillResult.error(f"Claude API error: {e.response.status_code}")
        except httpx.RequestError as e:
            return SkillResult.error(f"Couldn't reach Claude API: {type(e).__name__}")

    async def __aenter__(self) -> "ClaudeSkill":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.client.aclose()

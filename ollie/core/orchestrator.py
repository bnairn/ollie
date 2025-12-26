"""Main orchestrator that routes queries to skills."""

import asyncio
from rich.console import Console

from .skill import Skill, SkillConfidence, SkillMatch, SkillResult


class Orchestrator:
    """Routes user queries to appropriate skills."""

    def __init__(self) -> None:
        self.skills: list[Skill] = []
        self.console = Console()

    def register(self, skill: Skill) -> None:
        """Register a skill with the orchestrator."""
        self.skills.append(skill)
        self.console.print(f"[dim]Registered skill: {skill.name}[/dim]")

    async def process(self, query: str) -> SkillResult:
        """
        Process a user query by finding the best matching skill.

        Args:
            query: The user's natural language query

        Returns:
            SkillResult from the matched skill, or a fallback response
        """
        query = query.strip()
        if not query:
            return SkillResult.error("I didn't catch that. Could you say it again?")

        # Get matches from all skills concurrently
        matches = await asyncio.gather(
            *[skill.match(query) for skill in self.skills]
        )

        # Find the best match
        best_match: SkillMatch | None = None
        for match in matches:
            if match.confidence == SkillConfidence.NO_MATCH:
                continue
            if best_match is None or match.confidence.value > best_match.confidence.value:
                best_match = match

        if best_match is None:
            return self._fallback_response(query)

        # Execute the matched skill
        try:
            return await best_match.skill.execute(query, best_match.extracted)
        except Exception as e:
            self.console.print(f"[red]Skill error: {e}[/red]")
            return SkillResult.error(
                f"Sorry, I had trouble with that. {best_match.skill.name} encountered an error."
            )

    def _fallback_response(self, query: str) -> SkillResult:
        """Generate a fallback response when no skill matches."""
        # In the future, this could use the LLM for general conversation
        return SkillResult(
            success=True,
            response=(
                "I'm not sure how to help with that yet. "
                "I can help with weather, news, timers, jokes, flights, travel times, and recipes."
            ),
        )

    def list_skills(self) -> list[dict[str, str]]:
        """List all registered skills."""
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "examples": skill.examples,
            }
            for skill in self.skills
        ]

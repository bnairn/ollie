"""Base skill interface and result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SkillConfidence(Enum):
    """How confident a skill is that it can handle a query."""

    NO_MATCH = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    EXACT = 4


@dataclass
class SkillResult:
    """Result from a skill execution."""

    success: bool
    response: str
    data: dict[str, Any] = field(default_factory=dict)
    speak: str | None = None  # Optional different text for TTS

    @classmethod
    def error(cls, message: str) -> "SkillResult":
        """Create an error result."""
        return cls(success=False, response=message)

    @classmethod
    def ok(cls, response: str, **data: Any) -> "SkillResult":
        """Create a successful result."""
        return cls(success=True, response=response, data=data)


@dataclass
class SkillMatch:
    """A skill's claim that it can handle a query."""

    skill: "Skill"
    confidence: SkillConfidence
    extracted: dict[str, Any] = field(default_factory=dict)  # Extracted entities


class Skill(ABC):
    """Base class for all OLLIE skills."""

    name: str = "unnamed"
    description: str = "No description"
    examples: list[str] = []  # Example phrases this skill handles

    @abstractmethod
    async def match(self, query: str) -> SkillMatch:
        """
        Check if this skill can handle the query.

        Returns a SkillMatch with confidence level and any extracted entities.
        """
        pass

    @abstractmethod
    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """
        Execute the skill for the given query.

        Args:
            query: The user's original query
            extracted: Entities extracted during matching

        Returns:
            SkillResult with the response
        """
        pass

    def _no_match(self) -> SkillMatch:
        """Helper to return a no-match result."""
        return SkillMatch(skill=self, confidence=SkillConfidence.NO_MATCH)

    def _match(
        self, confidence: SkillConfidence, **extracted: Any
    ) -> SkillMatch:
        """Helper to return a match result."""
        return SkillMatch(skill=self, confidence=confidence, extracted=extracted)

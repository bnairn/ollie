"""Jokes skill - tell jokes (fully offline capable)."""

import random
import re
from typing import Any

from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class JokesSkill(Skill):
    """Tell jokes from a local collection."""

    name = "jokes"
    description = "Tell jokes and be entertaining"
    examples = [
        "Tell me a joke",
        "Make me laugh",
        "Know any good jokes?",
        "Tell me a dad joke",
    ]

    MATCH_PATTERNS = [
        r"tell\s+(?:me\s+)?(?:a\s+)?joke",
        r"(?:got|know|have)\s+(?:any\s+)?(?:good\s+)?jokes?",
        r"make\s+me\s+laugh",
        r"(?:say|tell)\s+something\s+funny",
        r"dad\s+joke",
        r"(?:a\s+)?joke\s+please",
    ]

    # A collection of clean, family-friendly jokes
    JOKES = [
        ("Why don't scientists trust atoms?", "Because they make up everything!"),
        ("What do you call a fake noodle?", "An impasta!"),
        (
            "Why did the scarecrow win an award?",
            "Because he was outstanding in his field!",
        ),
        (
            "I told my wife she was drawing her eyebrows too high.",
            "She looked surprised.",
        ),
        ("What do you call a bear with no teeth?", "A gummy bear!"),
        (
            "Why don't eggs tell jokes?",
            "They'd crack each other up!",
        ),
        (
            "What did the ocean say to the beach?",
            "Nothing, it just waved.",
        ),
        (
            "Why did the bicycle fall over?",
            "Because it was two-tired!",
        ),
        (
            "What do you call a fish without eyes?",
            "A fsh!",
        ),
        (
            "I'm reading a book about anti-gravity.",
            "It's impossible to put down!",
        ),
        (
            "Why did the math book look so sad?",
            "Because it had too many problems.",
        ),
        (
            "What do you call a sleeping dinosaur?",
            "A dino-snore!",
        ),
        (
            "I used to hate facial hair...",
            "But then it grew on me.",
        ),
        (
            "What did the left eye say to the right eye?",
            "Between you and me, something smells.",
        ),
        (
            "Why can't you give Elsa a balloon?",
            "Because she'll let it go!",
        ),
        (
            "What do you call a factory that makes okay products?",
            "A satisfactory!",
        ),
        (
            "I'm on a seafood diet.",
            "I see food and I eat it!",
        ),
        (
            "Why did the golfer bring two pairs of pants?",
            "In case he got a hole in one!",
        ),
        (
            "What do you call a dog that does magic tricks?",
            "A Labracadabrador!",
        ),
        (
            "Why did the coffee file a police report?",
            "It got mugged!",
        ),
    ]

    def __init__(self) -> None:
        self.last_joke_index: int | None = None

    async def match(self, query: str) -> SkillMatch:
        """Check if user wants a joke."""
        query_lower = query.lower()

        # Check for inappropriate joke requests - still match but flag it
        inappropriate = any(
            word in query_lower
            for word in ["dirty", "adult", "explicit", "nsfw", "rude", "offensive"]
        )
        if inappropriate and "joke" in query_lower:
            return self._match(SkillConfidence.HIGH, family_friendly_only=True)

        for pattern in self.MATCH_PATTERNS:
            if re.search(pattern, query_lower):
                return self._match(SkillConfidence.HIGH)

        # Weak match for "funny" or "laugh"
        if any(word in query_lower for word in ["funny", "laugh", "humor", "humour"]):
            return self._match(SkillConfidence.LOW)

        return self._no_match()

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Tell a joke."""
        # Handle inappropriate requests gracefully
        if extracted.get("family_friendly_only"):
            return SkillResult.ok(
                "I only know family-friendly jokes! Here's a clean one instead:\n\n"
                + self._get_random_joke()
            )

        # Pick a random joke, avoiding the last one told
        available_indices = [
            i for i in range(len(self.JOKES)) if i != self.last_joke_index
        ]
        joke_index = random.choice(available_indices)
        self.last_joke_index = joke_index

        setup, punchline = self.JOKES[joke_index]

        # Format nicely
        response = f"{setup}\n\n{punchline}"

        return SkillResult.ok(
            response,
            setup=setup,
            punchline=punchline,
        )

    def _get_random_joke(self) -> str:
        """Get a random joke as formatted string."""
        available_indices = [
            i for i in range(len(self.JOKES)) if i != self.last_joke_index
        ]
        joke_index = random.choice(available_indices)
        self.last_joke_index = joke_index
        setup, punchline = self.JOKES[joke_index]
        return f"{setup}\n\n{punchline}"

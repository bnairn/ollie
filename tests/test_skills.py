"""Tests for OLLIE skills."""

import pytest
from ollie.core.skill import SkillConfidence
from ollie.skills import TimerSkill, JokesSkill


class TestTimerSkill:
    """Test the timer skill."""

    @pytest.fixture
    def skill(self):
        return TimerSkill()

    async def test_match_set_timer(self, skill):
        """Test matching timer set commands."""
        match = await skill.match("set a timer for 5 minutes")
        assert match.confidence == SkillConfidence.HIGH
        assert match.extracted["action"] == "set"
        assert match.extracted["duration_seconds"] == 300

    async def test_match_list_timers(self, skill):
        """Test matching timer list commands."""
        match = await skill.match("what timers are running?")
        assert match.confidence == SkillConfidence.HIGH
        assert match.extracted["action"] == "list"

    async def test_match_cancel_timer(self, skill):
        """Test matching timer cancel commands."""
        match = await skill.match("cancel the timer")
        assert match.confidence == SkillConfidence.HIGH
        assert match.extracted["action"] == "cancel"

    async def test_no_match(self, skill):
        """Test non-timer queries don't match."""
        match = await skill.match("what's the weather?")
        assert match.confidence == SkillConfidence.NO_MATCH

    async def test_execute_set_timer(self, skill):
        """Test setting a timer."""
        result = await skill.execute(
            "set a timer for 1 minute",
            {"action": "set", "duration_seconds": 60},
        )
        assert result.success
        assert "1 minute" in result.response
        assert len(skill.timers) == 1

    async def test_execute_list_empty(self, skill):
        """Test listing when no timers exist."""
        result = await skill.execute("list timers", {"action": "list"})
        assert result.success
        assert "No timers" in result.response


class TestJokesSkill:
    """Test the jokes skill."""

    @pytest.fixture
    def skill(self):
        return JokesSkill()

    async def test_match_tell_joke(self, skill):
        """Test matching joke requests."""
        match = await skill.match("tell me a joke")
        assert match.confidence == SkillConfidence.HIGH

    async def test_match_make_laugh(self, skill):
        """Test alternative joke phrases."""
        match = await skill.match("make me laugh")
        assert match.confidence == SkillConfidence.HIGH

    async def test_no_match(self, skill):
        """Test non-joke queries don't match."""
        match = await skill.match("set a timer")
        assert match.confidence == SkillConfidence.NO_MATCH

    async def test_execute_returns_joke(self, skill):
        """Test that execute returns a joke."""
        result = await skill.execute("tell me a joke", {})
        assert result.success
        assert result.data.get("setup")
        assert result.data.get("punchline")

    async def test_different_jokes(self, skill):
        """Test that we get different jokes on repeated calls."""
        jokes = set()
        for _ in range(5):
            result = await skill.execute("joke", {})
            jokes.add(result.data["setup"])
        # Should have at least 2 different jokes in 5 attempts
        assert len(jokes) >= 2

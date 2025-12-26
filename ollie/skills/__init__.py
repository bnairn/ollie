"""OLLIE Skills - pluggable capabilities."""

from .timer import TimerSkill
from .jokes import JokesSkill
from .weather import WeatherSkill
from .travel import TravelSkill
from .conversions import ConversionsSkill
from .flights import FlightsSkill
from .recipes import RecipesSkill
from .math import MathSkill
from .sonos import SonosSkill
from .claude import ClaudeSkill
from .time import TimeSkill
from .aircraft import AircraftSkill

__all__ = [
    "TimerSkill",
    "JokesSkill",
    "WeatherSkill",
    "TravelSkill",
    "ConversionsSkill",
    "FlightsSkill",
    "RecipesSkill",
    "MathSkill",
    "SonosSkill",
    "ClaudeSkill",
    "TimeSkill",
    "AircraftSkill",
]

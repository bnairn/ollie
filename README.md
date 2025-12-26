# OLLIE - Offline Local Language Intelligence

A privacy-focused, locally-hosted voice assistant for Raspberry Pi 5.

**Why OLLIE?** Unlike Google Assistant, Siri, or Alexa, OLLIE processes everything locally and only makes API calls for specific skills you configure. Your conversations never go to big tech companies.

## Features

- **12 Built-in Skills**: Weather, timers, jokes, unit conversions, travel times, flights, recipes, math, time zones, Sonos control, and Claude AI fallback
- **Privacy First**: No always-listening cloud services
- **Extensible**: Easy to add new skills
- **Voice Ready**: Designed for Whisper STT + Piper TTS (text mode for development)

## Quick Start

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install OLLIE
pip install -e .

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Run text-mode prototype
python -m ollie.cli
```

## Example Queries

| Skill | Example |
|-------|---------|
| Weather | "What's the weather?" / "Weather in Tokyo" |
| Timer | "Set a timer for 5 minutes" / "What timers are running?" |
| Jokes | "Tell me a joke" |
| Conversions | "How many tablespoons in a cup?" / "$100 USD in euros" |
| Travel | "How long to drive from Seattle to Portland?" |
| Flights | "What time is AS549 arriving?" |
| Recipes | "Give me a recipe for chocolate chip cookies" |
| Math | "What's 9 times 9?" |
| Time | "What time is it in Israel?" |
| Sonos | "Play music" / "Pause" / "Volume up" / "What's playing?" |
| Claude | Any general question falls back to Claude AI |

## Project Structure

```
ollie/
├── ollie/
│   ├── core/              # Core framework
│   │   ├── config.py      # Pydantic settings from .env
│   │   ├── orchestrator.py # Routes queries to skills
│   │   └── skill.py       # Base skill class
│   ├── skills/            # Individual skills
│   │   ├── timer.py       # Set/list/cancel timers
│   │   ├── jokes.py       # Family-friendly jokes
│   │   ├── weather.py     # OpenWeatherMap integration
│   │   ├── travel.py      # OpenRouteService driving times
│   │   ├── conversions.py # Unit & currency conversions
│   │   ├── flights.py     # FlightAware AeroAPI
│   │   ├── recipes.py     # Spoonacular API
│   │   ├── math.py        # Basic arithmetic
│   │   ├── time.py        # World time zones
│   │   ├── sonos.py       # Sonos speaker control
│   │   └── claude.py      # Claude AI fallback
│   └── cli.py             # Text-mode interface
├── tests/
├── models/                # LLM models (gitignored)
├── .env.example           # API key template
├── pyproject.toml         # Dependencies
└── Makefile
```

## API Keys

All services have free tiers. Configure in `.env`:

| Service | Purpose | Free Tier | Get Key |
|---------|---------|-----------|---------|
| OpenWeatherMap | Weather | 1000 calls/day | [openweathermap.org](https://openweathermap.org/api) |
| OpenRouteService | Driving times | 2000 calls/day | [openrouteservice.org](https://openrouteservice.org) |
| Spoonacular | Recipes | 150 calls/day | [spoonacular.com](https://spoonacular.com/food-api) |
| AeroAPI | Flight status | Limited free | [flightaware.com](https://flightaware.com/aeroapi/) |
| Anthropic | Claude AI | Pay-as-you-go | [console.anthropic.com](https://console.anthropic.com) |

## Hardware Target

- **Raspberry Pi 5** (8GB RAM)
- **ReSpeaker XVF3800** USB mic array
- **Dayton PC83-4** speaker
- **Sonos** integration for whole-home audio

## How It Works

1. Wake word detection (OpenWakeWord) - runs locally
2. Speech-to-text (Whisper.cpp) - runs locally
3. Query routing (Orchestrator) - runs locally
4. Skill execution - some skills call external APIs
5. Text-to-speech (Piper TTS) - runs locally

The only network traffic is from skills that explicitly need it (weather, flights, etc.). General conversation with Claude only happens when no other skill matches.

## Development Roadmap

- [x] Phase 1: Text-mode prototype with skills
- [ ] Phase 2: Add Whisper STT + Piper TTS
- [ ] Phase 3: Add wake word detection
- [ ] Phase 4: Deploy to Raspberry Pi 5

## Adding New Skills

Create a new file in `ollie/skills/`:

```python
from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult

class MySkill(Skill):
    name = "myskill"
    description = "Does something cool"
    examples = ["Example query 1", "Example query 2"]

    async def match(self, query: str) -> SkillMatch:
        # Return confidence level based on query
        if "trigger word" in query.lower():
            return self._match(SkillConfidence.HIGH)
        return self._no_match()

    async def execute(self, query: str, extracted: dict) -> SkillResult:
        # Do the work and return result
        return SkillResult.ok("Response text", speak="TTS version")
```

Then register it in `ollie/cli.py` and `ollie/skills/__init__.py`.

## License

MIT

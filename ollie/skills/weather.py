"""Weather skill - get weather forecasts via OpenWeatherMap API."""

import re
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class WeatherSkill(Skill):
    """Get current weather and forecasts."""

    name = "weather"
    description = "Get weather information for any location"
    examples = [
        "What's the weather?",
        "Weather in London",
        "Is it going to rain today?",
        "What's the temperature?",
        "Do I need an umbrella?",
    ]

    MATCH_PATTERNS = [
        r"(?:what(?:'s| is) (?:the )?)?weather",
        r"(?:what(?:'s| is) (?:the )?)?temperature",
        r"(?:is it|will it) (?:going to )?rain",
        r"(?:do i|should i) (?:need )?(?:an? )?umbrella",
        r"(?:is it|how) (?:cold|hot|warm|chilly)",
        r"forecast",
    ]

    # Weather condition to emoji mapping
    WEATHER_ICONS = {
        "clear": "☀️",
        "clouds": "☁️",
        "rain": "🌧️",
        "drizzle": "🌦️",
        "thunderstorm": "⛈️",
        "snow": "❄️",
        "mist": "🌫️",
        "fog": "🌫️",
        "haze": "🌫️",
    }

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=10.0)

    async def match(self, query: str) -> SkillMatch:
        """Check if user wants weather info."""
        query_lower = query.lower()

        for pattern in self.MATCH_PATTERNS:
            if re.search(pattern, query_lower):
                location = self._extract_location(query)
                return self._match(SkillConfidence.HIGH, location=location)

        return self._no_match()

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Get weather for the location."""
        if not self.settings.openweathermap_api_key:
            return SkillResult.error(
                "Weather isn't configured yet. Add OPENWEATHERMAP_API_KEY to your .env file."
            )

        location = extracted.get("location") or self.settings.default_location

        try:
            weather = await self._fetch_weather(location)
            if weather is None:
                # Fallback to configured lat/lon for default location
                if location == self.settings.default_location:
                    weather = await self._fetch_weather_by_coords(
                        self.settings.default_lat,
                        self.settings.default_lon,
                        location,
                    )
                else:
                    return SkillResult.error(
                        f"I couldn't find '{location}'. Try a larger city nearby."
                    )
            return self._format_response(weather, location)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return SkillResult.error(
                    "Weather API key is invalid. Check your OPENWEATHERMAP_API_KEY in .env"
                )
            if e.response.status_code == 404:
                return SkillResult.error(f"I couldn't find weather for '{location}'.")
            return SkillResult.error(
                f"Weather API error: {e.response.status_code} - {e.response.text[:100]}"
            )
        except httpx.RequestError as e:
            return SkillResult.error(
                f"I couldn't reach the weather service: {type(e).__name__}"
            )

    async def _fetch_weather(self, location: str) -> dict[str, Any] | None:
        """Fetch weather from OpenWeatherMap API."""
        # First, geocode the location
        geo_url = "https://api.openweathermap.org/geo/1.0/direct"
        geo_response = await self.client.get(
            geo_url,
            params={
                "q": location,
                "limit": 1,
                "appid": self.settings.openweathermap_api_key,
            },
        )
        geo_response.raise_for_status()
        geo_data = geo_response.json()

        if not geo_data:
            return None  # Signal that location wasn't found

        lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
        resolved_name = geo_data[0].get("name", location)

        # Now get the weather
        weather_url = "https://api.openweathermap.org/data/2.5/weather"
        weather_response = await self.client.get(
            weather_url,
            params={
                "lat": lat,
                "lon": lon,
                "appid": self.settings.openweathermap_api_key,
                "units": "metric",  # Use metric, convert in display if needed
            },
        )
        weather_response.raise_for_status()
        weather_data = weather_response.json()
        weather_data["resolved_name"] = resolved_name

        return weather_data

    async def _fetch_weather_by_coords(
        self, lat: float, lon: float, display_name: str
    ) -> dict[str, Any]:
        """Fetch weather using lat/lon coordinates directly."""
        weather_url = "https://api.openweathermap.org/data/2.5/weather"
        weather_response = await self.client.get(
            weather_url,
            params={
                "lat": lat,
                "lon": lon,
                "appid": self.settings.openweathermap_api_key,
                "units": "metric",
            },
        )
        weather_response.raise_for_status()
        weather_data = weather_response.json()
        weather_data["resolved_name"] = display_name
        return weather_data

    def _format_response(self, weather: dict[str, Any], location: str) -> SkillResult:
        """Format weather data into a nice response."""
        main = weather.get("main", {})
        weather_info = weather.get("weather", [{}])[0]
        wind = weather.get("wind", {})
        resolved_name = weather.get("resolved_name", location)

        temp_c = main.get("temp", 0)
        temp_f = temp_c * 9 / 5 + 32
        feels_like_c = main.get("feels_like", temp_c)
        feels_like_f = feels_like_c * 9 / 5 + 32
        humidity = main.get("humidity", 0)
        description = weather_info.get("description", "unknown").title()
        condition = weather_info.get("main", "").lower()
        wind_speed = wind.get("speed", 0) * 3.6  # m/s to km/h

        icon = self.WEATHER_ICONS.get(condition, "🌡️")

        response = (
            f"{icon} {resolved_name}: {description}\n"
            f"Temperature: {temp_c:.0f}°C ({temp_f:.0f}°F)\n"
            f"Feels like: {feels_like_c:.0f}°C ({feels_like_f:.0f}°F)\n"
            f"Humidity: {humidity}%\n"
            f"Wind: {wind_speed:.0f} km/h"
        )

        # TTS-friendly version
        speak = (
            f"In {resolved_name}, it's {description} with a temperature of "
            f"{temp_c:.0f} degrees celsius, feels like {feels_like_c:.0f}. "
            f"Humidity is {humidity} percent."
        )

        return SkillResult(
            success=True,
            response=response,
            speak=speak,
            data={
                "location": resolved_name,
                "temp_c": temp_c,
                "temp_f": temp_f,
                "description": description,
                "humidity": humidity,
            },
        )

    def _extract_location(self, query: str) -> str | None:
        """Extract location from the query."""
        query_lower = query.lower()

        # Pattern: "weather in <location>" or "weather for <location>"
        patterns = [
            r"weather (?:in|for|at) ([a-zA-Z\s,]+?)(?:\?|$|\.)",
            r"(?:temperature|forecast) (?:in|for|at) ([a-zA-Z\s,]+?)(?:\?|$|\.)",
        ]

        for pattern in patterns:
            if match := re.search(pattern, query_lower):
                location = match.group(1).strip()
                # Clean up common trailing words
                for word in ["today", "tomorrow", "right now", "currently"]:
                    location = location.replace(word, "").strip()
                if location:
                    return location.title()

        return None

    async def __aenter__(self) -> "WeatherSkill":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.client.aclose()

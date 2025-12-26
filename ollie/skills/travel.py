"""Travel time skill - get driving/walking/cycling times via OpenRouteService."""

import re
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class TravelSkill(Skill):
    """Get travel times between locations."""

    name = "travel"
    description = "Get travel times and distances between locations"
    examples = [
        "How long to drive to Seattle?",
        "How far is it to Portland?",
        "Travel time to Bellevue",
        "How long would it take to get to the airport?",
    ]

    MATCH_PATTERNS = [
        r"how (?:long|far|much time).*(?:to get to|to drive to|to reach|to travel to|to go to)\s+(.+)",
        r"(?:driving|travel|drive)\s+time\s+(?:to|from)\s+(.+)",
        r"how long.*drive.*(?:to|from)\s+(.+)",
        r"(?:distance|how far).*(?:to|from)\s+(.+)",
    ]

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=15.0)

    async def match(self, query: str) -> SkillMatch:
        """Check if user wants travel time info."""
        query_lower = query.lower()

        for pattern in self.MATCH_PATTERNS:
            if match := re.search(pattern, query_lower):
                destination = self._clean_destination(match.group(1))
                return self._match(SkillConfidence.HIGH, destination=destination)

        # Check for simpler patterns
        if any(phrase in query_lower for phrase in ["how long to", "drive to", "travel to"]):
            return self._match(SkillConfidence.MEDIUM, destination=None)

        return self._no_match()

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Get travel time to destination."""
        if not self.settings.openrouteservice_api_key:
            return SkillResult.error(
                "Travel times aren't configured. Add OPENROUTESERVICE_API_KEY to your .env file."
            )

        destination = extracted.get("destination")
        if not destination:
            # Try to extract from query again
            destination = self._extract_destination(query)

        if not destination:
            return SkillResult.error(
                "Where would you like to go? Try 'How long to drive to Seattle?'"
            )

        try:
            # Geocode origin (default location)
            origin_coords = await self._geocode(self.settings.default_location)
            if not origin_coords:
                # Use configured lat/lon as fallback
                origin_coords = (self.settings.default_lon, self.settings.default_lat)

            # Geocode destination
            dest_coords = await self._geocode(destination)
            if not dest_coords:
                return SkillResult.error(f"I couldn't find '{destination}' on the map.")

            # Get route
            route = await self._get_route(origin_coords, dest_coords)
            return self._format_response(route, destination)

        except httpx.HTTPStatusError as e:
            return SkillResult.error(
                f"Travel API error: {e.response.status_code}"
            )
        except httpx.RequestError as e:
            return SkillResult.error(
                f"Couldn't reach travel service: {type(e).__name__}"
            )

    async def _geocode(self, location: str) -> tuple[float, float] | None:
        """Geocode a location to coordinates using OpenRouteService."""
        url = "https://api.openrouteservice.org/geocode/search"
        response = await self.client.get(
            url,
            params={
                "api_key": self.settings.openrouteservice_api_key,
                "text": location,
                "size": 1,
            },
        )
        response.raise_for_status()
        data = response.json()

        features = data.get("features", [])
        if not features:
            return None

        coords = features[0]["geometry"]["coordinates"]
        return (coords[0], coords[1])  # lon, lat

    async def _get_route(
        self, origin: tuple[float, float], destination: tuple[float, float]
    ) -> dict[str, Any]:
        """Get driving route between two points."""
        url = "https://api.openrouteservice.org/v2/directions/driving-car"
        response = await self.client.get(
            url,
            params={
                "api_key": self.settings.openrouteservice_api_key,
                "start": f"{origin[0]},{origin[1]}",
                "end": f"{destination[0]},{destination[1]}",
            },
        )
        response.raise_for_status()
        return response.json()

    def _format_response(self, route: dict[str, Any], destination: str) -> SkillResult:
        """Format route data into a response."""
        features = route.get("features", [])
        if not features:
            return SkillResult.error("Couldn't calculate route.")

        props = features[0]["properties"]["segments"][0]
        duration_seconds = props.get("duration", 0)
        distance_meters = props.get("distance", 0)

        # Format duration
        hours, remainder = divmod(int(duration_seconds), 3600)
        minutes = remainder // 60

        if hours > 0:
            duration_str = f"{hours} hour{'s' if hours != 1 else ''} {minutes} minute{'s' if minutes != 1 else ''}"
        else:
            duration_str = f"{minutes} minute{'s' if minutes != 1 else ''}"

        # Format distance
        distance_km = distance_meters / 1000
        distance_miles = distance_km * 0.621371

        response = (
            f"🚗 To {destination}:\n"
            f"Drive time: {duration_str}\n"
            f"Distance: {distance_km:.1f} km ({distance_miles:.1f} miles)"
        )

        speak = (
            f"It would take about {duration_str} to drive to {destination}, "
            f"a distance of {distance_miles:.0f} miles."
        )

        return SkillResult(
            success=True,
            response=response,
            speak=speak,
            data={
                "destination": destination,
                "duration_seconds": duration_seconds,
                "duration_str": duration_str,
                "distance_km": distance_km,
                "distance_miles": distance_miles,
            },
        )

    def _clean_destination(self, text: str) -> str:
        """Clean up extracted destination text."""
        # Remove trailing punctuation and common words
        text = re.sub(r"[?.!]+$", "", text).strip()
        for suffix in ["from here", "from my location", "right now", "today"]:
            text = re.sub(rf"\s*{suffix}\s*$", "", text, flags=re.IGNORECASE)
        return text.strip()

    def _extract_destination(self, query: str) -> str | None:
        """Try to extract destination from query."""
        query_lower = query.lower()
        for pattern in self.MATCH_PATTERNS:
            if match := re.search(pattern, query_lower):
                return self._clean_destination(match.group(1))
        return None

    async def __aenter__(self) -> "TravelSkill":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.client.aclose()

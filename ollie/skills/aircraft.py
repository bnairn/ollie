"""Aircraft skill - track aircraft flying overhead using OpenSky Network."""

import re
from datetime import datetime
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class AircraftSkill(Skill):
    """Track aircraft flying overhead."""

    name = "aircraft"
    description = "See what aircraft are flying overhead"
    examples = [
        "What planes are flying over my house?",
        "Tell me about aircraft overhead",
        "What's that plane above me?",
        "Show me nearby aircraft",
    ]

    MATCH_PATTERNS = [
        r"(?:what|which)\s+(?:plane|aircraft|airplane)s?\s+(?:are\s+)?(?:flying\s+)?(?:over|above|nearby)",
        r"(?:tell\s+me\s+about|show\s+me)\s+(?:the\s+)?(?:plane|aircraft|airplane)s?\s+(?:over|above|nearby|overhead)",
        r"(?:what'?s?\s+)?(?:that\s+)?(?:plane|aircraft|airplane)\s+(?:over|above)\s+(?:me|my\s+house|us|here)",
        r"(?:plane|aircraft|airplane)s?\s+(?:flying\s+)?(?:over|above|nearby|overhead)",
        r"(?:what'?s?\s+)?flying\s+over(?:head)?",
        r"overhead\s+(?:plane|aircraft|airplane|traffic)",
    ]

    # Bounding box size in degrees (roughly 10-15 miles)
    SEARCH_RADIUS = 0.15  # ~10 miles at mid-latitudes

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=15.0)

    async def match(self, query: str) -> SkillMatch:
        """Check if user is asking about overhead aircraft."""
        query_lower = query.lower()

        for pattern in self.MATCH_PATTERNS:
            if re.search(pattern, query_lower):
                return self._match(SkillConfidence.HIGH)

        # Weak match for aircraft-related keywords
        if any(word in query_lower for word in ["plane", "aircraft", "airplane", "flying over"]):
            return self._match(SkillConfidence.LOW)

        return self._no_match()

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Get aircraft flying overhead."""
        lat = self.settings.default_lat
        lon = self.settings.default_lon

        try:
            aircraft = await self._get_nearby_aircraft(lat, lon)

            if not aircraft:
                return SkillResult.ok(
                    "I don't see any aircraft flying near you right now. "
                    "Try again in a few minutes - air traffic changes constantly.",
                    speak="No aircraft detected overhead right now.",
                )

            return self._format_response(aircraft, lat, lon)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                return SkillResult.error(
                    "Aircraft tracking rate limit exceeded. Try again in a few seconds."
                )
            return SkillResult.error(f"Aircraft tracking error: {e.response.status_code}")
        except httpx.RequestError as e:
            return SkillResult.error(f"Couldn't reach aircraft tracking service: {type(e).__name__}")

    async def _get_nearby_aircraft(self, lat: float, lon: float) -> list[dict[str, Any]]:
        """Query OpenSky Network for aircraft in bounding box."""
        # Create bounding box around location
        lamin = lat - self.SEARCH_RADIUS
        lamax = lat + self.SEARCH_RADIUS
        lomin = lon - self.SEARCH_RADIUS
        lomax = lon + self.SEARCH_RADIUS

        url = "https://opensky-network.org/api/states/all"
        params = {
            "lamin": lamin,
            "lamax": lamax,
            "lomin": lomin,
            "lomax": lomax,
        }

        # Use authentication if credentials are configured (better rate limits)
        auth = None
        if self.settings.opensky_username and self.settings.opensky_password:
            auth = (self.settings.opensky_username, self.settings.opensky_password)

        response = await self.client.get(url, params=params, auth=auth)
        response.raise_for_status()
        data = response.json()

        states = data.get("states", [])
        if not states:
            return []

        # Parse state vectors into readable format
        # Fields: https://openskynetwork.github.io/opensky-api/rest.html
        aircraft = []
        for state in states:
            if len(state) < 17:
                continue

            icao24 = state[0]
            callsign = (state[1] or "").strip()
            origin_country = state[2]
            longitude = state[5]
            latitude = state[6]
            baro_altitude = state[7]  # meters
            on_ground = state[8]
            velocity = state[9]  # m/s
            heading = state[10]  # degrees
            vertical_rate = state[11]  # m/s
            geo_altitude = state[13]  # meters

            # Skip aircraft on the ground
            if on_ground:
                continue

            # Use geometric altitude if available, else barometric
            altitude_m = geo_altitude if geo_altitude is not None else baro_altitude
            if altitude_m is None:
                continue

            # Convert to feet
            altitude_ft = int(altitude_m * 3.28084)

            # Convert velocity to knots
            speed_kts = int(velocity * 1.94384) if velocity else None

            # Calculate distance from user (simple approximation)
            if latitude and longitude:
                dist_deg = ((latitude - lat) ** 2 + (longitude - lon) ** 2) ** 0.5
                dist_miles = dist_deg * 69  # Rough conversion

            aircraft.append({
                "icao24": icao24,
                "callsign": callsign or "Unknown",
                "origin_country": origin_country,
                "altitude_ft": altitude_ft,
                "speed_kts": speed_kts,
                "heading": int(heading) if heading else None,
                "vertical_rate": vertical_rate,
                "distance_miles": round(dist_miles, 1) if latitude and longitude else None,
            })

        # Sort by distance
        aircraft.sort(key=lambda x: x.get("distance_miles") or 999)
        return aircraft

    def _format_response(self, aircraft: list[dict[str, Any]], lat: float, lon: float) -> SkillResult:
        """Format aircraft list into response."""
        count = len(aircraft)

        # Detailed info for closest aircraft
        lines = [f"**{count} aircraft nearby:**\n"]

        for i, ac in enumerate(aircraft[:5]):  # Show up to 5
            callsign = ac["callsign"]
            altitude = ac["altitude_ft"]
            speed = ac["speed_kts"]
            heading = ac["heading"]
            distance = ac["distance_miles"]
            country = ac["origin_country"]

            # Direction from heading
            direction = self._heading_to_direction(heading) if heading else ""

            line = f"• **{callsign}**"
            if distance:
                line += f" ({distance} mi away)"
            line += f" - {altitude:,} ft"
            if speed:
                line += f", {speed} kts"
            if direction:
                line += f" heading {direction}"
            if country:
                line += f" [{country}]"

            lines.append(line)

        if count > 5:
            lines.append(f"\n... and {count - 5} more aircraft")

        # Build TTS response
        closest = aircraft[0]
        if closest["callsign"] != "Unknown":
            speak = f"I see {count} aircraft nearby. The closest is {closest['callsign']} "
        else:
            speak = f"I see {count} aircraft nearby. The closest is "
        speak += f"at {closest['altitude_ft']:,} feet"
        if closest["distance_miles"]:
            speak += f", about {closest['distance_miles']} miles away"
        speak += "."

        return SkillResult(
            success=True,
            response="\n".join(lines),
            speak=speak,
            data={
                "count": count,
                "aircraft": aircraft[:5],
                "location": {"lat": lat, "lon": lon},
            },
        )

    def _heading_to_direction(self, heading: int) -> str:
        """Convert heading degrees to cardinal direction."""
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        index = round(heading / 45) % 8
        return directions[index]

    async def __aenter__(self) -> "AircraftSkill":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.client.aclose()

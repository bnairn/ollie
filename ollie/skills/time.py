"""Time skill - get current time in different locations."""

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class TimeSkill(Skill):
    """Get current time in different locations."""

    name = "time"
    description = "Get current time in different time zones"
    examples = [
        "What time is it?",
        "What time is it in Tokyo?",
        "Current time in London",
        "Time in Israel",
    ]

    # Common location to timezone mappings
    LOCATION_TIMEZONES = {
        # Countries
        "israel": "Asia/Jerusalem",
        "japan": "Asia/Tokyo",
        "china": "Asia/Shanghai",
        "india": "Asia/Kolkata",
        "australia": "Australia/Sydney",
        "uk": "Europe/London",
        "united kingdom": "Europe/London",
        "england": "Europe/London",
        "france": "Europe/Paris",
        "germany": "Europe/Berlin",
        "italy": "Europe/Rome",
        "spain": "Europe/Madrid",
        "russia": "Europe/Moscow",
        "brazil": "America/Sao_Paulo",
        "mexico": "America/Mexico_City",
        "canada": "America/Toronto",
        "korea": "Asia/Seoul",
        "south korea": "Asia/Seoul",
        "thailand": "Asia/Bangkok",
        "singapore": "Asia/Singapore",
        "philippines": "Asia/Manila",
        "vietnam": "Asia/Ho_Chi_Minh",
        "indonesia": "Asia/Jakarta",
        "malaysia": "Asia/Kuala_Lumpur",
        "uae": "Asia/Dubai",
        "dubai": "Asia/Dubai",
        "saudi arabia": "Asia/Riyadh",
        "egypt": "Africa/Cairo",
        "south africa": "Africa/Johannesburg",
        "nigeria": "Africa/Lagos",
        "kenya": "Africa/Nairobi",
        "morocco": "Africa/Casablanca",
        "new zealand": "Pacific/Auckland",
        "hawaii": "Pacific/Honolulu",
        "alaska": "America/Anchorage",
        "ireland": "Europe/Dublin",
        "netherlands": "Europe/Amsterdam",
        "belgium": "Europe/Brussels",
        "switzerland": "Europe/Zurich",
        "austria": "Europe/Vienna",
        "poland": "Europe/Warsaw",
        "greece": "Europe/Athens",
        "turkey": "Europe/Istanbul",
        "argentina": "America/Argentina/Buenos_Aires",
        "chile": "America/Santiago",
        "colombia": "America/Bogota",
        "peru": "America/Lima",
        # Cities
        "new york": "America/New_York",
        "nyc": "America/New_York",
        "los angeles": "America/Los_Angeles",
        "la": "America/Los_Angeles",
        "chicago": "America/Chicago",
        "denver": "America/Denver",
        "phoenix": "America/Phoenix",
        "seattle": "America/Los_Angeles",
        "san francisco": "America/Los_Angeles",
        "miami": "America/New_York",
        "boston": "America/New_York",
        "atlanta": "America/New_York",
        "dallas": "America/Chicago",
        "houston": "America/Chicago",
        "london": "Europe/London",
        "paris": "Europe/Paris",
        "berlin": "Europe/Berlin",
        "rome": "Europe/Rome",
        "madrid": "Europe/Madrid",
        "amsterdam": "Europe/Amsterdam",
        "moscow": "Europe/Moscow",
        "tokyo": "Asia/Tokyo",
        "beijing": "Asia/Shanghai",
        "shanghai": "Asia/Shanghai",
        "hong kong": "Asia/Hong_Kong",
        "taipei": "Asia/Taipei",
        "seoul": "Asia/Seoul",
        "mumbai": "Asia/Kolkata",
        "delhi": "Asia/Kolkata",
        "bangalore": "Asia/Kolkata",
        "sydney": "Australia/Sydney",
        "melbourne": "Australia/Melbourne",
        "brisbane": "Australia/Brisbane",
        "perth": "Australia/Perth",
        "auckland": "Pacific/Auckland",
        "toronto": "America/Toronto",
        "vancouver": "America/Vancouver",
        "montreal": "America/Montreal",
        "cairo": "Africa/Cairo",
        "johannesburg": "Africa/Johannesburg",
        "lagos": "Africa/Lagos",
        "nairobi": "Africa/Nairobi",
        "tel aviv": "Asia/Jerusalem",
        "jerusalem": "Asia/Jerusalem",
        "dubai": "Asia/Dubai",
        "bangkok": "Asia/Bangkok",
        "jakarta": "Asia/Jakarta",
        "kuala lumpur": "Asia/Kuala_Lumpur",
        "manila": "Asia/Manila",
        "ho chi minh": "Asia/Ho_Chi_Minh",
        "saigon": "Asia/Ho_Chi_Minh",
        "buenos aires": "America/Argentina/Buenos_Aires",
        "sao paulo": "America/Sao_Paulo",
        "rio": "America/Sao_Paulo",
        "rio de janeiro": "America/Sao_Paulo",
        "mexico city": "America/Mexico_City",
        "lisbon": "Europe/Lisbon",
        "dublin": "Europe/Dublin",
        "edinburgh": "Europe/London",
        "glasgow": "Europe/London",
        "zurich": "Europe/Zurich",
        "geneva": "Europe/Zurich",
        "vienna": "Europe/Vienna",
        "prague": "Europe/Prague",
        "budapest": "Europe/Budapest",
        "warsaw": "Europe/Warsaw",
        "stockholm": "Europe/Stockholm",
        "oslo": "Europe/Oslo",
        "copenhagen": "Europe/Copenhagen",
        "helsinki": "Europe/Helsinki",
        "athens": "Europe/Athens",
        "istanbul": "Europe/Istanbul",
    }

    # US timezone abbreviations
    US_TIMEZONES = {
        "eastern": "America/New_York",
        "est": "America/New_York",
        "edt": "America/New_York",
        "central": "America/Chicago",
        "cst": "America/Chicago",
        "cdt": "America/Chicago",
        "mountain": "America/Denver",
        "mst": "America/Denver",
        "mdt": "America/Denver",
        "pacific": "America/Los_Angeles",
        "pst": "America/Los_Angeles",
        "pdt": "America/Los_Angeles",
    }

    MATCH_PATTERNS = [
        r"what(?:'s|\s+is)\s+the\s+(?:current\s+)?time(?:\s+(?:in|at)\s+(.+?))?(?:\s+right\s+now)?[?\s]*$",
        r"(?:current\s+)?time\s+(?:in|at)\s+(.+?)[?\s]*$",
        r"what\s+time\s+is\s+it(?:\s+(?:in|at)\s+(.+?))?[?\s]*$",
        r"(?:tell\s+me\s+)?the\s+time(?:\s+(?:in|at)\s+(.+?))?[?\s]*$",
    ]

    async def match(self, query: str) -> SkillMatch:
        """Check if user is asking for the time."""
        query_lower = query.lower().strip()

        for pattern in self.MATCH_PATTERNS:
            if match := re.search(pattern, query_lower):
                location = match.group(1).strip() if match.group(1) else None
                return self._match(SkillConfidence.HIGH, location=location)

        # Weak match for time-related keywords
        if "time" in query_lower and any(word in query_lower for word in ["what", "current", "now"]):
            return self._match(SkillConfidence.LOW, location=None)

        return self._no_match()

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Get the current time."""
        location = extracted.get("location")

        if location:
            return self._get_time_for_location(location)
        else:
            return self._get_local_time()

    def _get_local_time(self) -> SkillResult:
        """Get local time."""
        now = datetime.now()
        time_str = now.strftime("%I:%M %p")
        date_str = now.strftime("%A, %B %d")

        return SkillResult(
            success=True,
            response=f"It's **{time_str}** on {date_str}.",
            speak=f"It's {time_str}.",
            data={"time": time_str, "date": date_str},
        )

    def _get_time_for_location(self, location: str) -> SkillResult:
        """Get time for a specific location."""
        location_lower = location.lower().strip()

        # Try direct location lookup
        tz_name = self.LOCATION_TIMEZONES.get(location_lower)

        # Try US timezone abbreviations
        if not tz_name:
            tz_name = self.US_TIMEZONES.get(location_lower)

        # Try to find a matching timezone in the database
        if not tz_name:
            tz_name = self._find_timezone(location_lower)

        if not tz_name:
            return SkillResult.error(
                f"I don't know the timezone for '{location}'. Try a major city or country name."
            )

        try:
            tz = ZoneInfo(tz_name)
            now = datetime.now(tz)
            time_str = now.strftime("%I:%M %p")
            date_str = now.strftime("%A, %B %d")

            # Get a friendly location name
            display_location = location.title()

            return SkillResult(
                success=True,
                response=f"It's **{time_str}** in {display_location} ({date_str}).",
                speak=f"It's {time_str} in {display_location}.",
                data={
                    "time": time_str,
                    "date": date_str,
                    "location": display_location,
                    "timezone": tz_name,
                },
            )
        except Exception:
            return SkillResult.error(f"Couldn't get the time for '{location}'.")

    def _find_timezone(self, location: str) -> str | None:
        """Try to find a timezone matching the location."""
        # Search through available timezones
        location_parts = location.replace(" ", "_").lower()

        for tz in available_timezones():
            tz_lower = tz.lower()
            if location_parts in tz_lower:
                return tz
            # Also check the city part (after the last /)
            city = tz.split("/")[-1].lower().replace("_", " ")
            if location == city:
                return tz

        return None

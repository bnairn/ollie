"""Flight status skill - check flight arrivals/departures via AeroAPI."""

import re
from datetime import datetime
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class FlightsSkill(Skill):
    """Check flight status and arrival times."""

    name = "flights"
    description = "Check flight status, arrival and departure times"
    examples = [
        "Is flight AA123 on time?",
        "When does UA456 arrive?",
        "Flight status for DL789",
        "What time does AS549 land?",
    ]

    MATCH_PATTERNS = [
        r"(?:flight|flt)\s*(?:status|info)?\s*(?:for\s+)?([A-Z]{2,3}\s*\d{1,4})",
        r"(?:is\s+)?(?:flight\s+)?([A-Z]{2,3}\s*\d{1,4})\s+(?:on\s+time|delayed|cancelled)",
        r"(?:when\s+)?(?:does|will|is)\s+(?:flight\s+)?([A-Z]{2,3}\s*\d{1,4})\s+(?:arrive|land|depart|take off)",
        r"(?:what\s+time\s+)?(?:does|will|is)\s+([A-Z]{2,3}\s*\d{1,4})\s+(?:scheduled|arriving|landing|departing)",
        r"([A-Z]{2,3}\s*\d{1,4})\s+(?:arrival|departure|status|eta)",
        r"where\s+is\s+(?:flight\s+)?([A-Z]{2,3}\s*\d{1,4})",
        r"(?:where\s+is\s+)?([A-Z]{2,3}\s*\d{1,4})\s+(?:going|headed|flying)",
        r"track\s+(?:flight\s+)?([A-Z]{2,3}\s*\d{1,4})",
    ]

    # Common airline codes for normalization
    AIRLINE_CODES = {
        "AS": "ASA",  # Alaska Airlines
        "AA": "AAL",  # American Airlines
        "DL": "DAL",  # Delta
        "UA": "UAL",  # United
        "WN": "SWA",  # Southwest
        "B6": "JBU",  # JetBlue
        "F9": "FFT",  # Frontier
        "NK": "NKS",  # Spirit
        "HA": "HAL",  # Hawaiian
    }

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=15.0)

    async def match(self, query: str) -> SkillMatch:
        """Check if user wants flight info."""
        query_upper = query.upper()

        for pattern in self.MATCH_PATTERNS:
            if match := re.search(pattern, query_upper):
                flight_number = match.group(1).replace(" ", "")
                return self._match(SkillConfidence.HIGH, flight_number=flight_number)

        # Check for flight-related keywords with a flight number pattern
        if re.search(r"[A-Z]{2,3}\s*\d{1,4}", query_upper):
            if any(word in query.lower() for word in ["flight", "arrive", "depart", "land", "eta", "delayed", "on time"]):
                match = re.search(r"([A-Z]{2,3}\s*\d{1,4})", query_upper)
                if match:
                    return self._match(SkillConfidence.MEDIUM, flight_number=match.group(1).replace(" ", ""))

        return self._no_match()

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Get flight status."""
        if not self.settings.aeroapi_key:
            return SkillResult.error(
                "Flight tracking isn't configured. Add AEROAPI_KEY to your .env file."
            )

        flight_number = extracted.get("flight_number", "")
        if not flight_number:
            return SkillResult.error("I couldn't find a flight number in your request.")

        # Normalize flight number (e.g., AS549 -> ASA549)
        flight_id = self._normalize_flight_number(flight_number)

        try:
            flight_info = await self._fetch_flight_info(flight_id)
            if not flight_info:
                # Try with original format
                flight_info = await self._fetch_flight_info(flight_number)

            if not flight_info:
                return SkillResult.error(
                    f"I couldn't find flight {flight_number}. Make sure it's a valid flight number."
                )

            return self._format_response(flight_info, flight_number)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return SkillResult.error("Flight API key is invalid. Check your AEROAPI_KEY.")
            if e.response.status_code == 404:
                return SkillResult.error(f"Flight {flight_number} not found.")
            return SkillResult.error(f"Flight API error: {e.response.status_code}")
        except httpx.RequestError as e:
            return SkillResult.error(f"Couldn't reach flight service: {type(e).__name__}")

    def _normalize_flight_number(self, flight_number: str) -> str:
        """Normalize flight number to AeroAPI format."""
        # Extract airline code and number
        match = re.match(r"([A-Z]{2,3})(\d+)", flight_number)
        if match:
            airline = match.group(1)
            number = match.group(2)
            # Convert 2-letter IATA to 3-letter ICAO if known
            if airline in self.AIRLINE_CODES:
                airline = self.AIRLINE_CODES[airline]
            return f"{airline}{number}"
        return flight_number

    async def _fetch_flight_info(self, flight_id: str) -> dict[str, Any] | None:
        """Fetch flight info from AeroAPI."""
        url = f"https://aeroapi.flightaware.com/aeroapi/flights/{flight_id}"

        response = await self.client.get(
            url,
            headers={
                "x-apikey": self.settings.aeroapi_key,
            },
        )
        response.raise_for_status()
        data = response.json()

        flights = data.get("flights", [])
        if not flights:
            return None

        # Return the most recent/relevant flight
        # Prefer flights that are scheduled for today or in progress
        now = datetime.utcnow()
        for flight in flights:
            scheduled = flight.get("scheduled_out") or flight.get("scheduled_off")
            if scheduled:
                try:
                    sched_time = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
                    # If flight is within last 24 hours or next 24 hours
                    diff_hours = abs((sched_time.replace(tzinfo=None) - now).total_seconds() / 3600)
                    if diff_hours < 24:
                        return flight
                except (ValueError, TypeError):
                    pass

        # Fall back to first flight
        return flights[0] if flights else None

    def _format_response(self, flight: dict[str, Any], original_number: str) -> SkillResult:
        """Format flight info into a response."""
        ident = flight.get("ident", original_number)
        origin = flight.get("origin", {})
        destination = flight.get("destination", {})
        status = flight.get("status", "Unknown")

        origin_code = origin.get("code_iata") or origin.get("code", "???")
        dest_code = destination.get("code_iata") or destination.get("code", "???")
        origin_city = origin.get("city", "")
        dest_city = destination.get("city", "")

        # Get times
        scheduled_arrival = flight.get("scheduled_in") or flight.get("scheduled_on")
        estimated_arrival = flight.get("estimated_in") or flight.get("estimated_on")
        actual_arrival = flight.get("actual_in") or flight.get("actual_on")

        scheduled_departure = flight.get("scheduled_out") or flight.get("scheduled_off")
        actual_departure = flight.get("actual_out") or flight.get("actual_off")

        # Format times
        def format_time(iso_time: str | None) -> str:
            if not iso_time:
                return "N/A"
            try:
                dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
                return dt.strftime("%I:%M %p")
            except (ValueError, TypeError):
                return iso_time

        sched_arr = format_time(scheduled_arrival)
        est_arr = format_time(estimated_arrival)
        act_arr = format_time(actual_arrival)
        sched_dep = format_time(scheduled_departure)

        # Determine status emoji
        status_lower = status.lower()
        if "landed" in status_lower or "arrived" in status_lower:
            emoji = "✅"
        elif "cancelled" in status_lower:
            emoji = "❌"
        elif "delayed" in status_lower:
            emoji = "⚠️"
        elif "en route" in status_lower or "airborne" in status_lower:
            emoji = "✈️"
        else:
            emoji = "🛫"

        # Build response
        lines = [
            f"{emoji} Flight {ident}: {status}",
            f"Route: {origin_code} ({origin_city}) → {dest_code} ({dest_city})",
        ]

        if actual_arrival:
            lines.append(f"Arrived: {act_arr}")
        elif estimated_arrival:
            lines.append(f"Estimated arrival: {est_arr}")
        elif scheduled_arrival:
            lines.append(f"Scheduled arrival: {sched_arr}")

        if sched_dep != "N/A":
            lines.append(f"Scheduled departure: {sched_dep}")

        response = "\n".join(lines)

        # TTS version
        speak = f"Flight {ident} from {origin_city or origin_code} to {dest_city or dest_code} is {status}."
        if estimated_arrival:
            speak += f" Estimated arrival at {est_arr}."
        elif scheduled_arrival:
            speak += f" Scheduled to arrive at {sched_arr}."

        return SkillResult(
            success=True,
            response=response,
            speak=speak,
            data={
                "flight": ident,
                "status": status,
                "origin": origin_code,
                "destination": dest_code,
                "scheduled_arrival": scheduled_arrival,
                "estimated_arrival": estimated_arrival,
            },
        )

    async def __aenter__(self) -> "FlightsSkill":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.client.aclose()

"""METAR skill - get aviation weather reports for airports."""

import re
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class MetarSkill(Skill):
    """Get METAR aviation weather reports for airports."""

    name = "metar"
    description = "Get METAR aviation weather reports"
    examples = [
        "What's the METAR for SeaTac?",
        "ATIS for Seattle Tacoma",
        "Airport weather for KSEA",
        "METAR KPAE",
    ]

    MATCH_PATTERNS = [
        r"(?:what(?:'s| is) (?:the )?)?metar\s+(?:for\s+)?(\w+)",
        r"(?:what(?:'s| is) (?:the )?)?atis\s+(?:for\s+)?(.+?)(?:\?|$)",
        r"airport\s+weather\s+(?:for\s+)?(.+?)(?:\?|$)",
        r"aviation\s+weather\s+(?:for\s+)?(.+?)(?:\?|$)",
        r"(?:get|give)\s+(?:me\s+)?(?:the\s+)?metar\s+(?:for\s+)?(\w+)",
    ]

    # Common airport name to ICAO code mappings
    AIRPORT_CODES = {
        # Pacific Northwest
        "seatac": "KSEA",
        "seattle": "KSEA",
        "seattle tacoma": "KSEA",
        "sea-tac": "KSEA",
        "paine": "KPAE",
        "paine field": "KPAE",
        "everett": "KPAE",
        "boeing field": "KBFI",
        "king county": "KBFI",
        "portland": "KPDX",
        "tacoma narrows": "KTIW",
        "olympia": "KOLM",
        "bellingham": "KBLI",
        "spokane": "KGEG",
        "yakima": "KYKM",
        # Major US airports
        "lax": "KLAX",
        "los angeles": "KLAX",
        "sfo": "KSFO",
        "san francisco": "KSFO",
        "jfk": "KJFK",
        "new york": "KJFK",
        "laguardia": "KLGA",
        "newark": "KEWR",
        "chicago": "KORD",
        "ohare": "KORD",
        "o'hare": "KORD",
        "midway": "KMDW",
        "denver": "KDEN",
        "atlanta": "KATL",
        "dallas": "KDFW",
        "dfw": "KDFW",
        "miami": "KMIA",
        "phoenix": "KPHX",
        "las vegas": "KLAS",
        "boston": "KBOS",
        "detroit": "KDTW",
        "minneapolis": "KMSP",
        "orlando": "KMCO",
        "honolulu": "PHNL",
        "anchorage": "PANC",
    }

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": "OLLIE Voice Assistant", "Accept": "application/geo+json"},
        )

    async def match(self, query: str) -> SkillMatch:
        """Check if user wants aviation weather."""
        query_lower = query.lower()

        # Direct pattern matches
        for pattern in self.MATCH_PATTERNS:
            if match := re.search(pattern, query_lower):
                airport = match.group(1).strip()
                return self._match(SkillConfidence.HIGH, airport=airport)

        # Check for ATIS/METAR keywords
        if "metar" in query_lower or "atis" in query_lower:
            # Try to extract airport from query
            airport = self._extract_airport(query_lower)
            if airport:
                return self._match(SkillConfidence.HIGH, airport=airport)
            return self._match(SkillConfidence.MEDIUM)

        return self._no_match()

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Get METAR for the airport."""
        airport = extracted.get("airport")

        if not airport:
            airport = self._extract_airport(query.lower())

        if not airport:
            return SkillResult.error(
                "Please specify an airport. Try 'METAR for Seattle' or 'METAR KSEA'."
            )

        # Convert airport name to ICAO code
        icao = self._get_icao_code(airport)

        try:
            obs = await self._fetch_observation(icao)
            if obs is None:
                return SkillResult.error(
                    f"Couldn't find weather for '{airport}'. "
                    "Try using the 4-letter ICAO code (e.g., KSEA for Seattle)."
                )
            return self._format_response(obs, icao)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return SkillResult.error(
                    f"Station '{icao}' not found. Use ICAO codes like KSEA, KLAX, etc."
                )
            return SkillResult.error(f"Weather API error: {e.response.status_code}")
        except httpx.RequestError as e:
            return SkillResult.error(f"Couldn't reach weather service: {type(e).__name__}")

    async def _fetch_observation(self, icao: str) -> dict[str, Any] | None:
        """Fetch latest observation from api.weather.gov."""
        url = f"https://api.weather.gov/stations/{icao}/observations/latest"

        response = await self.client.get(url)
        response.raise_for_status()

        data = response.json()
        props = data.get("properties", {})

        if not props:
            return None

        return props

    def _format_response(self, obs: dict[str, Any], icao: str) -> SkillResult:
        """Format observation data into response."""
        # Extract values from observation
        raw_metar = obs.get("rawMessage", "")
        station = obs.get("station", "").split("/")[-1] if obs.get("station") else icao
        timestamp = obs.get("timestamp", "")

        # Parse timestamp to get observation time
        obs_time = ""
        if timestamp:
            # Format: 2024-01-15T12:53:00+00:00
            try:
                obs_time = timestamp[11:16] + "Z"  # Extract HH:MM
            except (IndexError, TypeError):
                obs_time = timestamp

        # Wind
        wind_dir = obs.get("windDirection", {}).get("value")
        wind_speed = obs.get("windSpeed", {}).get("value")  # km/h from API
        wind_gust = obs.get("windGust", {}).get("value")  # km/h from API

        # Convert km/h to knots (1 km/h = 0.539957 knots)
        wind_spd_kt = int(wind_speed * 0.539957) if wind_speed else 0
        wind_gust_kt = int(wind_gust * 0.539957) if wind_gust else None
        wind_dir_str = str(int(wind_dir)).zfill(3) if wind_dir else "VRB"

        # Visibility (meters from API)
        vis_m = obs.get("visibility", {}).get("value")
        vis_sm = round(vis_m / 1609.34, 1) if vis_m else 10  # Convert to statute miles

        # Temperature and dewpoint (Celsius from API)
        temp_c = obs.get("temperature", {}).get("value")
        dew_c = obs.get("dewpoint", {}).get("value")

        # Barometric pressure (Pascals from API)
        pressure_pa = obs.get("barometricPressure", {}).get("value")
        altimeter = None
        if pressure_pa:
            # Convert Pa to inHg
            altimeter = f"{pressure_pa * 0.0002953:.2f}"

        # Cloud layers
        cloud_layers = obs.get("cloudLayers", [])
        clouds = []
        for layer in cloud_layers:
            amount = layer.get("amount", "")
            base = layer.get("base", {}).get("value")  # meters
            if amount and base:
                base_ft = int(base * 3.28084)
                clouds.append(f"{amount} {base_ft}")
            elif amount:
                clouds.append(amount)

        # Present weather
        present_wx = obs.get("presentWeather", [])
        weather = []
        for wx in present_wx:
            if wx.get("rawString"):
                weather.append(self._decode_weather(wx["rawString"]))

        # Text description from API
        text_desc = obs.get("textDescription", "")

        # Determine flight rules
        flight_rules = self._determine_flight_rules(clouds, str(vis_sm))

        cloud_str = ", ".join(clouds) if clouds else "Clear"
        wx_str = ", ".join(weather) if weather else ""

        # Build display response
        lines = [f"**{icao} Weather** ({flight_rules})"]
        if obs_time:
            lines.append(f"Observed: {obs_time}")
        lines.append("")

        # Wind
        if wind_spd_kt > 0:
            wind_line = f"Wind: {wind_dir_str}° at {wind_spd_kt} kt"
            if wind_gust_kt:
                wind_line += f", gusting {wind_gust_kt}"
        else:
            wind_line = "Wind: Calm"
        lines.append(wind_line)

        # Visibility
        lines.append(f"Visibility: {vis_sm} SM")

        # Clouds
        lines.append(f"Clouds: {cloud_str}")

        # Weather
        if wx_str:
            lines.append(f"Weather: {wx_str}")

        # Text description
        if text_desc:
            lines.append(f"Conditions: {text_desc}")

        # Temp/Dew
        if temp_c is not None:
            temp_f = int(temp_c * 9 / 5 + 32)
            temp_line = f"Temperature: {temp_c:.0f}°C ({temp_f}°F)"
            if dew_c is not None:
                dew_f = int(dew_c * 9 / 5 + 32)
                temp_line += f" / Dewpoint: {dew_c:.0f}°C ({dew_f}°F)"
            lines.append(temp_line)

        # Altimeter
        if altimeter:
            lines.append(f"Altimeter: {altimeter} inHg")

        if raw_metar:
            lines.append("")
            lines.append(f"Raw: `{raw_metar}`")

        # Build TTS response (ATIS-style)
        speak_parts = [f"{icao} weather."]

        # Wind for speech
        if wind_spd_kt > 0:
            if wind_dir_str == "VRB":
                speak_parts.append(f"Wind variable at {wind_spd_kt} knots.")
            else:
                speak_parts.append(f"Wind {wind_dir_str} degrees at {wind_spd_kt} knots.")
            if wind_gust_kt:
                speak_parts.append(f"Gusting to {wind_gust_kt}.")
        else:
            speak_parts.append("Wind calm.")

        # Visibility for speech
        if vis_sm >= 10:
            speak_parts.append("Visibility 10 miles or greater.")
        else:
            speak_parts.append(f"Visibility {vis_sm} miles.")

        # Use text description for conditions
        if text_desc:
            speak_parts.append(f"{text_desc}.")
        elif cloud_str and cloud_str != "Clear":
            speak_parts.append(f"Clouds {cloud_str} feet.")
        else:
            speak_parts.append("Sky clear.")

        # Temp for speech
        if temp_c is not None:
            temp_f = int(temp_c * 9 / 5 + 32)
            speak_parts.append(f"Temperature {temp_f} degrees.")

        # Altimeter for speech
        if altimeter:
            alt_str = altimeter.replace(".", " point ")
            speak_parts.append(f"Altimeter {alt_str}.")

        # Flight rules
        speak_parts.append(f"{flight_rules} conditions.")

        return SkillResult(
            success=True,
            response="\n".join(lines),
            speak=" ".join(speak_parts),
            data={
                "station": icao,
                "raw": raw_metar,
                "flight_rules": flight_rules,
                "temp_c": temp_c,
                "wind_dir": wind_dir_str,
                "wind_speed": wind_spd_kt,
            },
        )

    def _decode_weather(self, code: str) -> str:
        """Decode weather phenomenon code."""
        descriptions = {
            "-": "Light",
            "+": "Heavy",
            "VC": "Vicinity",
            "MI": "Shallow",
            "PR": "Partial",
            "BC": "Patches",
            "DR": "Drifting",
            "BL": "Blowing",
            "SH": "Showers",
            "TS": "Thunderstorm",
            "FZ": "Freezing",
            "DZ": "Drizzle",
            "RA": "Rain",
            "SN": "Snow",
            "SG": "Snow grains",
            "IC": "Ice crystals",
            "PL": "Ice pellets",
            "GR": "Hail",
            "GS": "Small hail",
            "UP": "Unknown precip",
            "BR": "Mist",
            "FG": "Fog",
            "FU": "Smoke",
            "VA": "Volcanic ash",
            "DU": "Dust",
            "SA": "Sand",
            "HZ": "Haze",
            "PY": "Spray",
            "PO": "Dust devils",
            "SQ": "Squall",
            "FC": "Funnel cloud",
            "SS": "Sandstorm",
            "DS": "Duststorm",
        }

        result = code
        for abbr, desc in descriptions.items():
            result = result.replace(abbr, desc + " ")
        return result.strip()

    def _determine_flight_rules(self, clouds: list[str], visibility: str) -> str:
        """Determine VFR/MVFR/IFR/LIFR based on ceiling and visibility."""
        # Find ceiling (lowest BKN or OVC)
        ceiling = 99999
        for cloud in clouds:
            # Format: "BKN 3500" or "OVC 1200"
            match = re.match(r"(BKN|OVC|VV)\s*(\d+)", cloud)
            if match:
                alt = int(match.group(2))
                ceiling = min(ceiling, alt)

        # Parse visibility
        try:
            vis = float(visibility.split()[0]) if visibility else 10
        except (ValueError, IndexError):
            vis = 10

        # Determine flight rules
        if ceiling < 500 or vis < 1:
            return "LIFR"
        elif ceiling < 1000 or vis < 3:
            return "IFR"
        elif ceiling <= 3000 or vis <= 5:
            return "MVFR"
        else:
            return "VFR"

    def _get_icao_code(self, airport: str) -> str:
        """Convert airport name to ICAO code."""
        airport_lower = airport.lower().strip()

        # Check if already an ICAO code (4 letters)
        if len(airport) == 4 and airport.isalpha():
            return airport.upper()

        # Check mapping
        if airport_lower in self.AIRPORT_CODES:
            return self.AIRPORT_CODES[airport_lower]

        # For US airports, try adding K prefix
        if len(airport) == 3 and airport.isalpha():
            return f"K{airport.upper()}"

        # Check for partial matches
        for name, code in self.AIRPORT_CODES.items():
            if airport_lower in name or name in airport_lower:
                return code

        # Return as-is (uppercase)
        return airport.upper()

    def _extract_airport(self, query: str) -> str | None:
        """Try to extract airport from query."""
        # Remove common words
        query = query.replace("what's the", "").replace("what is the", "")
        query = query.replace("metar for", "").replace("atis for", "")
        query = query.replace("airport weather for", "")
        query = query.replace("international airport", "").replace("airport", "")
        query = query.replace("?", "").strip()

        # Check if remaining text matches a known airport
        for name in self.AIRPORT_CODES:
            if name in query:
                return name

        # Look for 3-4 letter codes
        if match := re.search(r"\b([A-Za-z]{3,4})\b", query):
            return match.group(1)

        return query.strip() if query.strip() else None

    async def __aenter__(self) -> "MetarSkill":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.client.aclose()

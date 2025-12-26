"""Conversions skill - unit conversions and currency exchange."""

import re
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class ConversionsSkill(Skill):
    """Convert units, measurements, and currencies."""

    name = "conversions"
    description = "Convert units, measurements, and currencies"
    examples = [
        "How many quarts in a gallon?",
        "Convert 100 grams to ounces",
        "What is 72 kg in pounds?",
        "100 USD to EUR",
    ]

    # Unit conversion factors (to base unit)
    UNITS = {
        # Length (base: meters)
        "length": {
            "m": 1, "meter": 1, "meters": 1, "metre": 1, "metres": 1,
            "km": 1000, "kilometer": 1000, "kilometers": 1000, "kilometre": 1000,
            "cm": 0.01, "centimeter": 0.01, "centimeters": 0.01,
            "mm": 0.001, "millimeter": 0.001, "millimeters": 0.001,
            "mi": 1609.344, "mile": 1609.344, "miles": 1609.344,
            "yd": 0.9144, "yard": 0.9144, "yards": 0.9144,
            "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
            "in": 0.0254, "inch": 0.0254, "inches": 0.0254,
        },
        # Weight/Mass (base: grams)
        "weight": {
            "g": 1, "gram": 1, "grams": 1,
            "kg": 1000, "kilogram": 1000, "kilograms": 1000, "kilo": 1000, "kilos": 1000,
            "mg": 0.001, "milligram": 0.001, "milligrams": 0.001,
            "lb": 453.592, "lbs": 453.592, "pound": 453.592, "pounds": 453.592,
            "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
            "st": 6350.29, "stone": 6350.29, "stones": 6350.29,
            "t": 1000000, "ton": 907185, "tons": 907185, "tonne": 1000000, "tonnes": 1000000,
        },
        # Volume (base: liters)
        "volume": {
            "l": 1, "liter": 1, "liters": 1, "litre": 1, "litres": 1,
            "ml": 0.001, "milliliter": 0.001, "milliliters": 0.001,
            "gal": 3.78541, "gallon": 3.78541, "gallons": 3.78541,
            "qt": 0.946353, "quart": 0.946353, "quarts": 0.946353,
            "pt": 0.473176, "pint": 0.473176, "pints": 0.473176,
            "cup": 0.236588, "cups": 0.236588,
            "floz": 0.0295735, "fl oz": 0.0295735, "fluid ounce": 0.0295735, "fluid ounces": 0.0295735,
            "tbsp": 0.0147868, "tablespoon": 0.0147868, "tablespoons": 0.0147868,
            "tsp": 0.00492892, "teaspoon": 0.00492892, "teaspoons": 0.00492892,
        },
        # Temperature (special handling)
        "temperature": {
            "c": "celsius", "celsius": "celsius", "°c": "celsius",
            "f": "fahrenheit", "fahrenheit": "fahrenheit", "°f": "fahrenheit",
            "k": "kelvin", "kelvin": "kelvin",
        },
    }

    # Common currency codes
    CURRENCIES = {
        "usd": "USD", "dollar": "USD", "dollars": "USD", "$": "USD", "us dollar": "USD",
        "eur": "EUR", "euro": "EUR", "euros": "EUR", "€": "EUR",
        "gbp": "GBP", "pound": "GBP", "pounds": "GBP", "£": "GBP", "british pound": "GBP",
        "jpy": "JPY", "yen": "JPY", "¥": "JPY", "japanese yen": "JPY",
        "cad": "CAD", "canadian dollar": "CAD", "canadian dollars": "CAD",
        "aud": "AUD", "australian dollar": "AUD", "australian dollars": "AUD",
        "chf": "CHF", "swiss franc": "CHF", "swiss francs": "CHF",
        "cny": "CNY", "yuan": "CNY", "chinese yuan": "CNY", "rmb": "CNY",
        "inr": "INR", "rupee": "INR", "rupees": "INR", "indian rupee": "INR",
        "mxn": "MXN", "mexican peso": "MXN", "mexican pesos": "MXN", "peso": "MXN",
        "ils": "ILS", "shekel": "ILS", "shekels": "ILS", "sheqel": "ILS",
        "israeli shekel": "ILS", "israeli shekels": "ILS", "nis": "ILS",
        "krw": "KRW", "won": "KRW", "korean won": "KRW",
        "sgd": "SGD", "singapore dollar": "SGD",
        "nzd": "NZD", "new zealand dollar": "NZD",
        "sek": "SEK", "swedish krona": "SEK",
        "nok": "NOK", "norwegian krone": "NOK",
        "dkk": "DKK", "danish krone": "DKK",
        "php": "PHP", "philippine peso": "PHP",
        "thb": "THB", "thai baht": "THB", "baht": "THB",
    }

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=10.0)
        # Build reverse lookup for units
        self._unit_to_category: dict[str, str] = {}
        for category, units in self.UNITS.items():
            for unit in units:
                self._unit_to_category[unit.lower()] = category

    async def match(self, query: str) -> SkillMatch:
        """Check if user wants a conversion."""
        query_lower = query.lower()

        # Skip if this looks like a flight query (has flight number pattern)
        if re.search(r"\b[A-Z]{2,3}\s*\d{1,4}\b", query.upper()):
            if any(word in query_lower for word in ["flight", "arrive", "depart", "land", "scheduled", "eta", "delayed"]):
                return self._no_match()

        # Check for conversion patterns
        patterns = [
            r"(\d+(?:\.\d+)?)\s*(\w+)\s+(?:to|in|into|as)\s+(\w+)",  # "100 kg to lbs"
            r"how\s+many\s+(\w+)\s+(?:are\s+)?(?:in|per)\s+(?:a\s+)?(\w+)",  # "how many quarts in a gallon"
            r"convert\s+(\d+(?:\.\d+)?)\s*(\w+)\s+to\s+(\w+)",  # "convert 100 grams to ounces"
            r"what\s+is\s+(\d+(?:\.\d+)?)\s*(\w+)\s+in\s+(\w+)",  # "what is 72 kg in pounds"
            r"\$\s*(\d+(?:\.\d+)?)\s*(\w+)?\s+(?:to|in|into)\s+(\w+)",  # "$100 to euros"
            r"(\d+(?:\.\d+)?)\s*(\w+)\s+(?:is|=|equals?)\s+(?:how\s+many\s+)?(\w+)",  # "72 grams is how many ounces"
        ]

        for pattern in patterns:
            if re.search(pattern, query_lower):
                return self._match(SkillConfidence.HIGH)

        # Check for currency symbols or unit keywords
        if any(symbol in query_lower for symbol in ["$", "€", "£", "¥"]):
            if any(word in query_lower for word in ["to", "in", "convert"]):
                return self._match(SkillConfidence.HIGH)

        # Check if query mentions units we know
        words = re.findall(r'\w+', query_lower)
        known_units = sum(1 for w in words if w in self._unit_to_category or w in self.CURRENCIES)
        if known_units >= 2:
            return self._match(SkillConfidence.MEDIUM)

        return self._no_match()

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Perform the conversion."""
        query_lower = query.lower()

        # Try to parse the conversion request
        parsed = self._parse_conversion(query_lower)
        if not parsed:
            return SkillResult.error(
                "I couldn't understand that conversion. Try '100 kg to pounds' or 'how many cups in a gallon'."
            )

        value, from_unit, to_unit = parsed

        # Check if it's a currency conversion (try multi-word lookup)
        from_currency = self._lookup_currency(from_unit)
        to_currency = self._lookup_currency(to_unit)

        if from_currency and to_currency:
            return await self._convert_currency(value, from_currency, to_currency)

        # Check if it's a unit conversion
        from_category = self._unit_to_category.get(from_unit)
        to_category = self._unit_to_category.get(to_unit)

        if from_category and to_category:
            if from_category != to_category:
                return SkillResult.error(
                    f"Can't convert {from_unit} to {to_unit} - they're different types of measurements."
                )
            return self._convert_units(value, from_unit, to_unit, from_category)

        return SkillResult.error(
            f"I don't know how to convert '{from_unit}' to '{to_unit}'."
        )

    def _lookup_currency(self, text: str) -> str | None:
        """Look up a currency code from text, handling multi-word names."""
        text = text.lower().strip()

        # Direct lookup first
        if text in self.CURRENCIES:
            return self.CURRENCIES[text]

        # Try without trailing 's' (shekels -> shekel)
        if text.endswith('s') and text[:-1] in self.CURRENCIES:
            return self.CURRENCIES[text[:-1]]

        # Check if text contains any known currency name
        for name, code in self.CURRENCIES.items():
            if name in text or text in name:
                return code

        return None

    def _parse_conversion(self, query: str) -> tuple[float, str, str] | None:
        """Parse a conversion query into (value, from_unit, to_unit)."""

        # Number pattern that handles decimals and fractions like 1/4, 1/2
        num_pattern = r"(\d+(?:\.\d+)?(?:/\d+)?)"
        # Word fraction pattern
        word_frac_pattern = r"(half|third|quarter|fourth|fifth|eighth|three\s+quarters?|three\s+fourths?|two\s+thirds?)"

        # Handle "how many X in a quarter of a Y" style
        match = re.search(r"how\s+many\s+(\w+)\s+(?:are\s+)?(?:in|per)\s+(?:a\s+)?" + word_frac_pattern + r"\s+(?:of\s+)?(?:a\s+)?(\w+)", query)
        if match:
            to_unit = match.group(1)
            value_str = match.group(2).replace(" ", "")  # "three quarters" -> "threequarters"
            # Normalize for lookup
            value_str = match.group(2)
            from_unit = match.group(3)
            return (self._parse_number(value_str), from_unit, to_unit)

        # Handle "how many X in Y" with optional number (e.g., "how many tbsp in 1/4 cup")
        match = re.search(r"how\s+many\s+(\w+)\s+(?:are\s+)?(?:in|per)\s+(?:a\s+)?" + num_pattern + r"?\s*(\w+)", query)
        if match:
            to_unit = match.group(1)
            value_str = match.group(2) if match.group(2) else "1"
            from_unit = match.group(3)
            return (self._parse_number(value_str), from_unit, to_unit)

        # Handle "$100 USD to X" or "$100 to X"
        match = re.search(r"\$\s*" + num_pattern + r"\s*(?:usd?)?\s+(?:to|in|into|is)\s+(?:how\s+many\s+)?(.+?)(?:\?|$)", query)
        if match:
            to_currency = match.group(2).strip().rstrip("?")
            return (self._parse_number(match.group(1)), "usd", to_currency)

        # Handle "X grams is how many ounces"
        match = re.search(num_pattern + r"\s*(\w+)\s+(?:is|=|equals?)\s+(?:how\s+many\s+)?(\w+)", query)
        if match:
            return (self._parse_number(match.group(1)), match.group(2), match.group(3))

        # Handle "100 kg to lbs" or "100kg in pounds" or "1/4 cup to tbsp"
        match = re.search(num_pattern + r"\s*(\w+)\s+(?:to|in|into|as)\s+(\w+)", query)
        if match:
            return (self._parse_number(match.group(1)), match.group(2), match.group(3))

        # Handle "convert 100 grams to ounces"
        match = re.search(r"convert\s+" + num_pattern + r"\s*(\w+)\s+to\s+(\w+)", query)
        if match:
            return (self._parse_number(match.group(1)), match.group(2), match.group(3))

        # Handle "what is 72 kg in pounds"
        match = re.search(r"what\s+is\s+" + num_pattern + r"\s*(\w+)\s+in\s+(\w+)", query)
        if match:
            return (self._parse_number(match.group(1)), match.group(2), match.group(3))

        return None

    # Word-based fractions
    WORD_FRACTIONS = {
        "half": 0.5, "a half": 0.5,
        "third": 1/3, "a third": 1/3,
        "quarter": 0.25, "a quarter": 0.25,
        "fourth": 0.25, "a fourth": 0.25,
        "fifth": 0.2, "a fifth": 0.2,
        "eighth": 0.125, "an eighth": 0.125,
        "three quarters": 0.75, "three fourths": 0.75,
        "two thirds": 2/3,
    }

    def _parse_number(self, value_str: str) -> float:
        """Parse a number string, handling fractions like 1/4, 1/2, or 'quarter'."""
        value_str = value_str.strip().lower()

        # Check word-based fractions first
        if value_str in self.WORD_FRACTIONS:
            return self.WORD_FRACTIONS[value_str]

        if "/" in value_str:
            parts = value_str.split("/")
            if len(parts) == 2:
                try:
                    return float(parts[0]) / float(parts[1])
                except (ValueError, ZeroDivisionError):
                    return 1.0
        try:
            return float(value_str)
        except ValueError:
            return 1.0

    def _convert_units(
        self, value: float, from_unit: str, to_unit: str, category: str
    ) -> SkillResult:
        """Convert between units in the same category."""

        if category == "temperature":
            return self._convert_temperature(value, from_unit, to_unit)

        units = self.UNITS[category]
        from_factor = units.get(from_unit, 1)
        to_factor = units.get(to_unit, 1)

        # Convert to base unit, then to target unit
        base_value = value * from_factor
        result = base_value / to_factor

        # Format nicely
        if result == int(result):
            result_str = str(int(result))
        elif result >= 100:
            result_str = f"{result:.1f}"
        elif result >= 1:
            result_str = f"{result:.2f}"
        else:
            result_str = f"{result:.4f}".rstrip('0').rstrip('.')

        response = f"📐 {value} {from_unit} = {result_str} {to_unit}"
        speak = f"{value} {from_unit} equals {result_str} {to_unit}"

        return SkillResult(
            success=True,
            response=response,
            speak=speak,
            data={"value": value, "from": from_unit, "to": to_unit, "result": result},
        )

    def _convert_temperature(self, value: float, from_unit: str, to_unit: str) -> SkillResult:
        """Convert between temperature units."""
        temp_map = self.UNITS["temperature"]
        from_type = temp_map.get(from_unit)
        to_type = temp_map.get(to_unit)

        # Convert to Celsius first
        if from_type == "fahrenheit":
            celsius = (value - 32) * 5 / 9
        elif from_type == "kelvin":
            celsius = value - 273.15
        else:
            celsius = value

        # Convert from Celsius to target
        if to_type == "fahrenheit":
            result = celsius * 9 / 5 + 32
        elif to_type == "kelvin":
            result = celsius + 273.15
        else:
            result = celsius

        result_str = f"{result:.1f}"
        response = f"🌡️ {value}° {from_type.title()} = {result_str}° {to_type.title()}"
        speak = f"{value} degrees {from_type} equals {result_str} degrees {to_type}"

        return SkillResult(
            success=True,
            response=response,
            speak=speak,
            data={"value": value, "from": from_type, "to": to_type, "result": result},
        )

    async def _convert_currency(
        self, value: float, from_currency: str, to_currency: str
    ) -> SkillResult:
        """Convert between currencies using a free API."""
        try:
            # Using exchangerate-api.com (free tier, no key needed for basic use)
            url = f"https://open.er-api.com/v6/latest/{from_currency}"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get("result") != "success":
                return SkillResult.error("Couldn't get exchange rates right now.")

            rates = data.get("rates", {})
            if to_currency not in rates:
                return SkillResult.error(f"I don't have exchange rate data for {to_currency}.")

            rate = rates[to_currency]
            result = value * rate

            # Format with appropriate precision
            if result >= 100:
                result_str = f"{result:,.2f}"
            else:
                result_str = f"{result:.2f}"

            response_text = f"💱 {value:,.2f} {from_currency} = {result_str} {to_currency}"
            speak = f"{value} {from_currency} equals {result_str} {to_currency}"

            return SkillResult(
                success=True,
                response=response_text,
                speak=speak,
                data={
                    "value": value,
                    "from": from_currency,
                    "to": to_currency,
                    "rate": rate,
                    "result": result,
                },
            )
        except httpx.RequestError:
            return SkillResult.error("Couldn't reach the currency exchange service.")

    async def __aenter__(self) -> "ConversionsSkill":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.client.aclose()

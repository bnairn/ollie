"""Math skill - basic arithmetic calculations."""

import re
import math
from typing import Any

from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class MathSkill(Skill):
    """Handle basic math and arithmetic questions."""

    name = "math"
    description = "Basic math and arithmetic calculations"
    examples = [
        "What's 9 times 9?",
        "Calculate 15% of 200",
        "What is 144 divided by 12?",
        "Square root of 81",
    ]

    # Word to operator mapping
    WORD_OPERATORS = {
        "plus": "+",
        "add": "+",
        "added to": "+",
        "and": "+",
        "minus": "-",
        "subtract": "-",
        "less": "-",
        "take away": "-",
        "times": "*",
        "multiplied by": "*",
        "x": "*",
        "divided by": "/",
        "over": "/",
        "to the power of": "**",
        "squared": "**2",
        "cubed": "**3",
    }

    # Word to number mapping
    WORD_NUMBERS = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
        "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
        "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
        "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
        "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
    }

    async def match(self, query: str) -> SkillMatch:
        """Check if user wants a calculation."""
        query_lower = query.lower()

        # Direct math patterns
        patterns = [
            r"what(?:'s| is)\s+(\d+)\s+(?:times|plus|minus|divided by|multiplied by)\s+(\d+)",
            r"(?:calculate|compute|what is|what's)\s+.+(?:\+|\-|\*|\/|\%)",
            r"(\d+)\s*[\+\-\*\/\%]\s*(\d+)",
            r"(\d+)\s+(?:times|plus|minus|divided by|multiplied by)\s+(\d+)",
            r"(?:square root|sqrt|cube root)\s+(?:of\s+)?(\d+)",
            r"(\d+)\s+(?:squared|cubed)",
            r"(\d+)\s*(?:\%|percent)\s+of\s+(\d+)",
            r"what(?:'s| is)\s+(\d+)\s*(?:\%|percent)\s+of\s+(\d+)",
        ]

        for pattern in patterns:
            if re.search(pattern, query_lower):
                return self._match(SkillConfidence.HIGH, expression=query_lower)

        # Word-based math (nine times nine)
        for word in ["times", "plus", "minus", "divided", "multiplied", "add", "subtract"]:
            if word in query_lower:
                # Check if there are numbers (digit or word) on both sides
                if self._has_numbers(query_lower):
                    return self._match(SkillConfidence.HIGH, expression=query_lower)

        # Percentage questions
        if "percent" in query_lower or "%" in query:
            if self._has_numbers(query_lower):
                return self._match(SkillConfidence.MEDIUM, expression=query_lower)

        return self._no_match()

    def _has_numbers(self, text: str) -> bool:
        """Check if text contains at least two numbers (digits or words)."""
        count = 0
        # Count digit sequences
        count += len(re.findall(r"\d+", text))
        # Count number words
        for word in self.WORD_NUMBERS:
            if word in text.split():
                count += 1
        return count >= 2

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Perform the calculation."""
        expression = extracted.get("expression", query.lower())

        try:
            result = self._evaluate(expression)
            if result is None:
                return SkillResult.error(
                    "I couldn't parse that math expression. Try something like '9 times 9' or '15% of 200'."
                )

            # Format result nicely
            if result == int(result):
                result_str = str(int(result))
            else:
                result_str = f"{result:.4f}".rstrip("0").rstrip(".")

            # Create a natural response
            response = f"{result_str}"
            speak = f"The answer is {result_str}"

            return SkillResult(
                success=True,
                response=response,
                speak=speak,
                data={"result": result},
            )

        except Exception as e:
            return SkillResult.error(f"Calculation error: {str(e)}")

    def _evaluate(self, expression: str) -> float | None:
        """Evaluate a math expression."""
        expr = expression.lower().strip()

        # Handle square root
        match = re.search(r"(?:square root|sqrt)\s+(?:of\s+)?(\d+(?:\.\d+)?)", expr)
        if match:
            return math.sqrt(float(match.group(1)))

        # Handle cube root
        match = re.search(r"cube root\s+(?:of\s+)?(\d+(?:\.\d+)?)", expr)
        if match:
            return float(match.group(1)) ** (1/3)

        # Handle squared/cubed
        match = re.search(r"(\d+(?:\.\d+)?)\s+squared", expr)
        if match:
            return float(match.group(1)) ** 2

        match = re.search(r"(\d+(?:\.\d+)?)\s+cubed", expr)
        if match:
            return float(match.group(1)) ** 3

        # Handle percentage: "X% of Y" or "X percent of Y"
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s+of\s+(\d+(?:\.\d+)?)", expr)
        if match:
            percent = float(match.group(1))
            value = float(match.group(2))
            return (percent / 100) * value

        # Convert word numbers to digits
        expr = self._convert_word_numbers(expr)

        # Convert word operators to symbols
        for word, symbol in sorted(self.WORD_OPERATORS.items(), key=lambda x: -len(x[0])):
            expr = expr.replace(word, f" {symbol} ")

        # Extract just the math part
        # Look for patterns like "number operator number"
        match = re.search(r"(\d+(?:\.\d+)?)\s*([\+\-\*\/\%\^]|\*\*)\s*(\d+(?:\.\d+)?)", expr)
        if match:
            a = float(match.group(1))
            op = match.group(2)
            b = float(match.group(3))

            if op == "+":
                return a + b
            elif op == "-":
                return a - b
            elif op == "*":
                return a * b
            elif op == "/":
                if b == 0:
                    raise ValueError("Cannot divide by zero")
                return a / b
            elif op == "%":
                return a % b
            elif op in ("**", "^"):
                return a ** b

        # Try simple "number number" after operator conversion (e.g., "9 * 9")
        match = re.search(r"(\d+(?:\.\d+)?)\s*\*\*\s*(\d+(?:\.\d+)?)", expr)
        if match:
            return float(match.group(1)) ** float(match.group(2))

        return None

    def _convert_word_numbers(self, text: str) -> str:
        """Convert word numbers to digits."""
        words = text.split()
        result = []
        i = 0
        while i < len(words):
            word = words[i].lower().strip(",.?!")

            # Handle compound numbers like "twenty one"
            if word in self.WORD_NUMBERS:
                num = self.WORD_NUMBERS[word]
                # Check for compound (e.g., "twenty one" = 21)
                if i + 1 < len(words):
                    next_word = words[i + 1].lower().strip(",.?!")
                    if next_word in self.WORD_NUMBERS:
                        next_num = self.WORD_NUMBERS[next_word]
                        if num >= 20 and next_num < 10:
                            num = num + next_num
                            i += 1
                result.append(str(num))
            else:
                result.append(words[i])
            i += 1

        return " ".join(result)

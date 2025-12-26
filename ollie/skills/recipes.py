"""Recipe skill - find recipes via Spoonacular API."""

import re
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class RecipesSkill(Skill):
    """Find recipes and cooking instructions."""

    name = "recipes"
    description = "Find recipes and cooking instructions"
    examples = [
        "Give me a recipe for chocolate chip cookies",
        "How do I make lasagna?",
        "Recipe for chicken soup",
        "What's a good bread recipe?",
    ]

    MATCH_PATTERNS = [
        r"(?:give\s+me\s+)?(?:a\s+)?recipe\s+(?:for\s+)?(.+)",
        r"how\s+(?:do\s+)?(?:i\s+)?(?:make|cook|bake|prepare)\s+(.+)",
        r"(?:what'?s?\s+)?(?:a\s+)?(?:good\s+)?(.+?)\s+recipe",
        r"(?:can\s+you\s+)?(?:find|get|show)\s+(?:me\s+)?(?:a\s+)?recipe\s+(?:for\s+)?(.+)",
        r"i\s+(?:want|need)\s+(?:to\s+make|a\s+recipe\s+for)\s+(.+)",
    ]

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=15.0)

    async def match(self, query: str) -> SkillMatch:
        """Check if user wants a recipe."""
        query_lower = query.lower()

        for pattern in self.MATCH_PATTERNS:
            if match := re.search(pattern, query_lower):
                dish = match.group(1).strip().rstrip("?.")
                # Clean up common trailing words
                dish = re.sub(r"\s+(?:please|thanks|thank you)$", "", dish)
                return self._match(SkillConfidence.HIGH, dish=dish)

        # Weak match for food-related keywords
        if any(word in query_lower for word in ["recipe", "cook", "bake", "ingredient"]):
            return self._match(SkillConfidence.LOW, dish=None)

        return self._no_match()

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Get a recipe."""
        if not self.settings.spoonacular_api_key:
            return SkillResult.error(
                "Recipes aren't configured. Add SPOONACULAR_API_KEY to your .env file."
            )

        dish = extracted.get("dish")
        if not dish:
            return SkillResult.error("What would you like a recipe for?")

        try:
            # Search for recipes
            recipes = await self._search_recipes(dish)
            if not recipes:
                return SkillResult.error(
                    f"I couldn't find a recipe for '{dish}'. Try something else?"
                )

            # Get details for the first recipe
            recipe_id = recipes[0]["id"]
            recipe = await self._get_recipe_details(recipe_id)

            return self._format_response(recipe)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return SkillResult.error(
                    "Recipe API key is invalid. Check your SPOONACULAR_API_KEY."
                )
            if e.response.status_code == 402:
                return SkillResult.error(
                    "Recipe API quota exceeded. Try again tomorrow."
                )
            return SkillResult.error(f"Recipe API error: {e.response.status_code}")
        except httpx.RequestError as e:
            return SkillResult.error(f"Couldn't reach recipe service: {type(e).__name__}")

    # Foods that are often used as ingredients but users likely want to make from scratch
    BASIC_FOODS = [
        "bread", "pasta", "noodles", "tortilla", "pizza dough", "pie crust",
        "cake", "cookies", "muffins", "pancakes", "waffles", "biscuits",
        "crackers", "pretzels", "bagels", "rolls", "buns",
    ]

    async def _search_recipes(self, dish: str) -> list[dict[str, Any]]:
        """Search for recipes matching a dish."""
        url = "https://api.spoonacular.com/recipes/complexSearch"
        dish_lower = dish.lower()

        # For basic foods, modify search to get actual recipes not dishes using them
        is_basic_food = any(basic in dish_lower for basic in self.BASIC_FOODS)

        # Build search params
        params = {
            "apiKey": self.settings.spoonacular_api_key,
            "query": dish,
            "number": 10,
            "instructionsRequired": True,
        }

        # For basic foods like bread, search by type
        if is_basic_food:
            # Add "recipe" to help find actual recipes
            params["titleMatch"] = dish  # Title must contain the dish name
            params["sort"] = "popularity"

        response = await self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])

        if not results and is_basic_food:
            # Try again without titleMatch but with recipe keyword
            params.pop("titleMatch", None)
            params["query"] = f"{dish} recipe"
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])

        # For basic foods, filter to prefer recipes that are actually making the item
        if is_basic_food and results:
            # Look for recipes where the title suggests making the item from scratch
            scratch_keywords = ["homemade", "easy", "simple", "basic", "classic", "best"]
            for r in results:
                title_lower = r.get("title", "").lower()
                # Prefer titles like "Homemade White Bread" over "Sandwich with White Bread"
                if dish_lower in title_lower:
                    # Check if title starts with the dish or a scratch keyword
                    if any(title_lower.startswith(kw) for kw in scratch_keywords + [dish_lower]):
                        return [r]
                    # Or if it's just the dish name with adjectives
                    words = title_lower.split()
                    if len(words) <= 4 and any(basic in title_lower for basic in self.BASIC_FOODS):
                        return [r]

            # Fall back to first result with dish in title
            for r in results:
                if dish_lower in r.get("title", "").lower():
                    return [r]

        return results[:1] if results else []

    async def _get_recipe_details(self, recipe_id: int) -> dict[str, Any]:
        """Get full recipe details including ingredients and instructions."""
        url = f"https://api.spoonacular.com/recipes/{recipe_id}/information"
        response = await self.client.get(
            url,
            params={
                "apiKey": self.settings.spoonacular_api_key,
                "includeNutrition": False,
            },
        )
        response.raise_for_status()
        return response.json()

    def _format_response(self, recipe: dict[str, Any]) -> SkillResult:
        """Format recipe into a response."""
        title = recipe.get("title", "Recipe")
        servings = recipe.get("servings", "?")
        ready_in = recipe.get("readyInMinutes", "?")

        # Get ingredients
        ingredients = recipe.get("extendedIngredients", [])
        ingredient_lines = []
        for ing in ingredients:
            original = ing.get("original", "")
            if original:
                ingredient_lines.append(f"  - {original}")

        # Get instructions
        instructions = []
        analyzed = recipe.get("analyzedInstructions", [])
        if analyzed:
            steps = analyzed[0].get("steps", [])
            for step in steps:
                num = step.get("number", "")
                text = step.get("step", "")
                if text:
                    instructions.append(f"  {num}. {text}")
        else:
            # Fall back to HTML instructions
            html_instructions = recipe.get("instructions", "")
            if html_instructions:
                # Strip HTML tags
                clean = re.sub(r"<[^>]+>", "", html_instructions)
                instructions.append(f"  {clean}")

        # Build response
        lines = [
            f"**{title}**",
            f"Servings: {servings} | Time: {ready_in} minutes",
            "",
            "**Ingredients:**",
        ]
        lines.extend(ingredient_lines[:15])  # Limit ingredients shown
        if len(ingredient_lines) > 15:
            lines.append(f"  ... and {len(ingredient_lines) - 15} more")

        lines.append("")
        lines.append("**Instructions:**")
        lines.extend(instructions[:10])  # Limit steps shown
        if len(instructions) > 10:
            lines.append(f"  ... and {len(instructions) - 10} more steps")

        response = "\n".join(lines)

        # TTS version (abbreviated)
        speak = f"Here's a recipe for {title}. It serves {servings} and takes about {ready_in} minutes. "
        if ingredients:
            speak += f"You'll need {len(ingredients)} ingredients. "
        if instructions:
            speak += f"There are {len(instructions)} steps. Would you like me to read the full recipe?"

        return SkillResult(
            success=True,
            response=response,
            speak=speak,
            data={
                "title": title,
                "servings": servings,
                "ready_in_minutes": ready_in,
                "ingredient_count": len(ingredients),
                "step_count": len(instructions),
                "source_url": recipe.get("sourceUrl"),
            },
        )

    async def __aenter__(self) -> "RecipesSkill":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.client.aclose()

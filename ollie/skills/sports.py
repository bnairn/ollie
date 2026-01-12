"""Sports skill - get live scores and sports news via ESPN API."""

import re
from datetime import datetime
from typing import Any, Optional

import httpx

from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class SportsSkill(Skill):
    """Get live sports scores and news."""

    name = "sports"
    description = "Get live sports scores, standings, and news"
    examples = [
        "What's the football score?",
        "How did the Seahawks do?",
        "NFL scores",
        "NBA scores today",
        "Did the Lakers win?",
        "Baseball scores",
        "Sports news",
    ]

    MATCH_PATTERNS = [
        r"(?:sports?|game|match|score)s?",
        r"(?:nfl|nba|mlb|nhl|football|basketball|baseball|hockey)",
        r"(?:seahawks?|49ers?|cowboys?|chiefs?|eagles?|ravens?|bills?|lions?|packers?)",
        r"(?:lakers?|celtics?|warriors?|bucks?|nuggets?|heat|suns?|76ers|sixers)",
        r"(?:yankees?|dodgers?|braves?|astros?|phillies?|rangers?|diamondbacks?)",
        r"(?:who (?:won|lost|is winning|is playing))",
        r"(?:did .+ win|did .+ lose)",
        r"(?:standings?|playoffs?|championship)",
    ]

    # ESPN API endpoints (unofficial but widely used)
    ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

    # Sport mappings
    SPORTS = {
        "nfl": ("football", "nfl"),
        "football": ("football", "nfl"),
        "nba": ("basketball", "nba"),
        "basketball": ("basketball", "nba"),
        "mlb": ("baseball", "mlb"),
        "baseball": ("baseball", "mlb"),
        "nhl": ("hockey", "nhl"),
        "hockey": ("hockey", "nhl"),
        "soccer": ("soccer", "usa.1"),  # MLS
        "mls": ("soccer", "usa.1"),
    }

    # Team name mappings (partial list - add more as needed)
    NFL_TEAMS = {
        "seahawks": "SEA", "49ers": "SF", "niners": "SF", "cowboys": "DAL",
        "chiefs": "KC", "eagles": "PHI", "ravens": "BAL", "bills": "BUF",
        "lions": "DET", "packers": "GB", "bears": "CHI", "vikings": "MIN",
        "saints": "NO", "falcons": "ATL", "buccaneers": "TB", "bucs": "TB",
        "panthers": "CAR", "rams": "LAR", "cardinals": "ARI", "chargers": "LAC",
        "raiders": "LV", "broncos": "DEN", "patriots": "NE", "jets": "NYJ",
        "giants": "NYG", "dolphins": "MIA", "commanders": "WAS", "steelers": "PIT",
        "browns": "CLE", "bengals": "CIN", "colts": "IND", "texans": "HOU",
        "titans": "TEN", "jaguars": "JAX",
    }

    NBA_TEAMS = {
        "lakers": "LAL", "celtics": "BOS", "warriors": "GSW", "bucks": "MIL",
        "nuggets": "DEN", "heat": "MIA", "suns": "PHX", "76ers": "PHI",
        "sixers": "PHI", "nets": "BKN", "knicks": "NYK", "bulls": "CHI",
        "cavaliers": "CLE", "cavs": "CLE", "mavericks": "DAL", "mavs": "DAL",
        "rockets": "HOU", "clippers": "LAC", "grizzlies": "MEM", "timberwolves": "MIN",
        "wolves": "MIN", "pelicans": "NOP", "thunder": "OKC", "magic": "ORL",
        "kings": "SAC", "spurs": "SAS", "raptors": "TOR", "jazz": "UTA",
        "wizards": "WAS", "hawks": "ATL", "hornets": "CHA", "pistons": "DET",
        "pacers": "IND", "trail blazers": "POR", "blazers": "POR",
    }

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=10.0)

    async def match(self, query: str) -> SkillMatch:
        """Check if query is asking about sports."""
        query_lower = query.lower()

        for pattern in self.MATCH_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return SkillMatch(
                    skill=self,
                    confidence=SkillConfidence.HIGH,
                    extracted={"query": query},
                )

        return SkillMatch(skill=self, confidence=SkillConfidence.NO_MATCH)

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Get sports scores or news."""
        query_lower = query.lower()

        try:
            # Determine which sport
            sport_key = self._detect_sport(query_lower)

            # Check for specific team
            team = self._detect_team(query_lower)

            # Get scores
            if sport_key:
                scores = await self._get_scores(sport_key, team)
                if scores:
                    return SkillResult(
                        success=True,
                        response=scores,
                        speak=self._make_speakable(scores),
                    )

            # Default: get headlines from multiple sports
            headlines = await self._get_headlines()
            if headlines:
                return SkillResult(
                    success=True,
                    response=headlines,
                    speak=self._make_speakable(headlines),
                )

            return SkillResult(
                success=False,
                response="I couldn't find any sports information right now.",
            )

        except Exception as e:
            return SkillResult(
                success=False,
                response=f"Error getting sports data: {e}",
            )

    def _detect_sport(self, query: str) -> Optional[str]:
        """Detect which sport is being asked about."""
        for keyword, sport_tuple in self.SPORTS.items():
            if keyword in query:
                return keyword
        # Check for team names to infer sport
        for team in self.NFL_TEAMS:
            if team in query:
                return "nfl"
        for team in self.NBA_TEAMS:
            if team in query:
                return "nba"
        return None

    def _detect_team(self, query: str) -> Optional[str]:
        """Detect if a specific team is mentioned."""
        for team_name, abbrev in {**self.NFL_TEAMS, **self.NBA_TEAMS}.items():
            if team_name in query:
                return team_name
        return None

    async def _get_scores(self, sport: str, team: Optional[str] = None) -> str:
        """Get scores for a sport."""
        if sport not in self.SPORTS:
            return ""

        sport_path, league = self.SPORTS[sport]
        url = f"{self.ESPN_BASE}/{sport_path}/{league}/scoreboard"

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

            events = data.get("events", [])
            if not events:
                return f"No {sport.upper()} games scheduled today."

            results = []
            for event in events[:5]:  # Limit to 5 games
                competition = event.get("competitions", [{}])[0]
                competitors = competition.get("competitors", [])

                if len(competitors) >= 2:
                    home = competitors[0]
                    away = competitors[1]

                    home_team = home.get("team", {}).get("abbreviation", "???")
                    away_team = away.get("team", {}).get("abbreviation", "???")
                    home_score = home.get("score", "0")
                    away_score = away.get("score", "0")

                    status = event.get("status", {}).get("type", {}).get("shortDetail", "")

                    # Filter by team if specified
                    if team:
                        team_abbrev = self.NFL_TEAMS.get(team) or self.NBA_TEAMS.get(team)
                        if team_abbrev and team_abbrev not in (home_team, away_team):
                            continue

                    results.append(f"{away_team} {away_score} @ {home_team} {home_score} ({status})")

            if results:
                header = f"**{sport.upper()} Scores:**\n"
                return header + "\n".join(results)
            elif team:
                return f"No games found for {team.title()} today."
            else:
                return f"No {sport.upper()} games found."

        except httpx.HTTPError as e:
            return f"Couldn't fetch {sport.upper()} scores."

    async def _get_headlines(self) -> str:
        """Get sports headlines."""
        url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news"

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

            articles = data.get("articles", [])[:3]
            if not articles:
                return "No sports news available right now."

            headlines = ["**Sports Headlines:**"]
            for article in articles:
                headline = article.get("headline", "")
                if headline:
                    headlines.append(f"- {headline}")

            return "\n".join(headlines)

        except httpx.HTTPError:
            return "Couldn't fetch sports news."

    def _make_speakable(self, text: str) -> str:
        """Convert formatted text to speakable form."""
        # Remove markdown
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        # Replace @ with "at"
        text = text.replace(" @ ", " at ")
        # Limit length for TTS
        lines = text.split("\n")
        if len(lines) > 4:
            lines = lines[:4]
            lines.append("And more.")
        return "\n".join(lines)

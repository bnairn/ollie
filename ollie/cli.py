#!/usr/bin/env python3
"""OLLIE CLI - Text-mode interface for testing."""

import asyncio
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .core import Orchestrator
from .core.config import get_settings
from .voice.tts import TTS
from .skills import (
    TimerSkill,
    JokesSkill,
    WeatherSkill,
    TravelSkill,
    ConversionsSkill,
    FlightsSkill,
    RecipesSkill,
    MathSkill,
    SonosSkill,
    ClaudeSkill,
    TimeSkill,
    AircraftSkill,
)


def timer_complete_handler(timer) -> None:
    """Handle timer completion - print notification."""
    console = Console()
    console.print(f"\n🔔 [bold yellow]Timer complete: {timer.name}![/bold yellow]")
    console.print("[dim]Press Enter to continue...[/dim]", end="")


async def async_main() -> None:
    """Main async entry point."""
    console = Console()
    settings = get_settings()

    # Initialize TTS if enabled
    tts = None
    if settings.tts_enabled:
        tts = TTS()
        if tts.piper_available:
            console.print("[dim]TTS enabled (Piper)[/dim]")
        else:
            console.print("[dim]TTS unavailable - install piper for voice output[/dim]")
            tts = None

    # Print welcome banner
    console.print(
        Panel.fit(
            "[bold blue]OLLIE[/bold blue] - Offline Local Language Intelligence\n"
            "[dim]Text-mode prototype • Type 'help' for commands • 'quit' to exit[/dim]",
            border_style="blue",
        )
    )

    # Initialize orchestrator and skills
    orchestrator = Orchestrator()

    # Register skills
    timer_skill = TimerSkill(on_timer_complete=timer_complete_handler)
    orchestrator.register(timer_skill)
    orchestrator.register(JokesSkill())
    orchestrator.register(WeatherSkill())
    orchestrator.register(TravelSkill())
    orchestrator.register(ConversionsSkill())
    orchestrator.register(FlightsSkill())
    orchestrator.register(RecipesSkill())
    orchestrator.register(MathSkill())
    orchestrator.register(SonosSkill())
    orchestrator.register(ClaudeSkill())
    orchestrator.register(TimeSkill())
    orchestrator.register(AircraftSkill())

    console.print()

    # Main loop
    while True:
        try:
            # Get user input
            query = Prompt.ask("[bold green]You[/bold green]")

            # Handle special commands
            if query.lower() in ("quit", "exit", "q"):
                console.print("[dim]Goodbye![/dim]")
                break

            if query.lower() == "help":
                _show_help(console, orchestrator)
                continue

            if query.lower() == "skills":
                _show_skills(console, orchestrator)
                continue

            if not query.strip():
                continue

            # Process the query
            result = await orchestrator.process(query)

            # Display response
            if result.success:
                console.print(f"[bold blue]OLLIE[/bold blue]: {result.response}")
            else:
                console.print(f"[bold red]OLLIE[/bold red]: {result.response}")

            # Speak the response
            if tts:
                # Use speak text if available (optimized for TTS), otherwise use response
                speak_text = result.speak if result.speak else result.response
                await tts.speak(speak_text)

            console.print()

        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye![/dim]")
            break
        except EOFError:
            break


def _show_help(console: Console, orchestrator: Orchestrator) -> None:
    """Show help information."""
    console.print(
        Panel(
            "[bold]Commands:[/bold]\n"
            "  help   - Show this help\n"
            "  skills - List available skills\n"
            "  quit   - Exit OLLIE\n\n"
            "[bold]Example queries:[/bold]\n"
            "  • What's the weather?\n"
            "  • Set a timer for 5 minutes\n"
            "  • Tell me a joke\n"
            "  • What timers are running?",
            title="Help",
            border_style="green",
        )
    )


def _show_skills(console: Console, orchestrator: Orchestrator) -> None:
    """List all available skills."""
    skills = orchestrator.list_skills()
    lines = []
    for skill in skills:
        lines.append(f"[bold]{skill['name']}[/bold]: {skill['description']}")
        if skill["examples"]:
            for example in skill["examples"][:2]:
                lines.append(f"  [dim]• {example}[/dim]")
    console.print(Panel("\n".join(lines), title="Available Skills", border_style="cyan"))


def main() -> None:
    """Entry point."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()

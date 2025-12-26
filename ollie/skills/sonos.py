"""Sonos skill - control Sonos speakers on the local network."""

import re
from typing import Any

import soco
from soco.exceptions import SoCoException

try:
    from soco.music_services import MusicService
    HAS_MUSIC_SERVICES = True
except ImportError:
    HAS_MUSIC_SERVICES = False

from ..core.config import get_settings
from ..core.skill import Skill, SkillConfidence, SkillMatch, SkillResult


class SonosSkill(Skill):
    """Control Sonos speakers."""

    name = "sonos"
    description = "Control Sonos speakers - play, pause, volume, and more"
    examples = [
        "Play music",
        "Pause the music",
        "Skip this song",
        "Volume up",
        "What's playing?",
        "Play music in the living room",
    ]

    # Action patterns
    PLAY_PATTERNS = [
        r"(?:play|start|resume)\s+(?:the\s+)?(?:music|song|audio)?",
        r"(?:play|start)\s+(?:some\s+)?music",
        r"unpause",
    ]

    PAUSE_PATTERNS = [
        r"(?:pause|stop)\s+(?:the\s+)?(?:music|song|audio|playback)?",
        r"pause",
        r"stop\s+(?:the\s+)?music",
    ]

    SKIP_PATTERNS = [
        r"(?:skip|next)\s+(?:this\s+)?(?:song|track)?",
        r"next\s+song",
        r"play\s+next",
    ]

    PREVIOUS_PATTERNS = [
        r"(?:previous|last|go\s+back)\s+(?:song|track)?",
        r"play\s+previous",
    ]

    VOLUME_PATTERNS = [
        r"(?:set\s+)?volume\s+(?:to\s+)?(\d+)",
        r"volume\s+(up|down|louder|quieter|softer)",
        r"turn\s+(?:it\s+)?(up|down)",
        r"(?:make\s+it|turn\s+it)\s+(louder|quieter|softer)",
        r"\b(mute|unmute)\b",
    ]

    WHATS_PLAYING_PATTERNS = [
        r"what(?:'s|\s+is)\s+(?:this\s+)?(?:song|playing|on)",
        r"what\s+song\s+is\s+(?:this|playing)",
        r"(?:current|now)\s+playing",
        r"what\s+are\s+we\s+listening\s+to",
    ]

    PLAY_FAVORITE_PATTERNS = [
        r"play\s+(?:my\s+)?(?:favorite|playlist|station)\s+(.+)",
        r"play\s+(.+)",
        r"^(?:pandora|spotify|amazon|apple|tidal)\s+(.+)",  # "pandora liquid funk..."
    ]

    # Room extraction pattern - matches "in/on [the] <room> [speaker] [on sonos]"
    ROOM_PATTERN = r"(?:in|on)\s+(?:the\s+)?(\w+(?:\s+\w+)?)\s*(?:room|speaker)?(?:\s+on\s+sonos)?$"

    # Patterns to strip from favorite name
    STRIP_PATTERNS = [
        r"\s+(?:from|on|via)\s+(?:pandora|spotify|amazon|apple|tidal|sonos).*",
        r"\s+(?:in|on)\s+(?:the\s+)?(?:\w+\s+)?(?:room|speaker).*",
        r"\s+on\s+sonos.*",
        r"\s+(?:playlist|station|radio)$",
        r"^(?:pandora|spotify|amazon|apple|tidal)\s+",  # Strip service name at start
    ]

    # Known music service names
    MUSIC_SERVICES = ["pandora", "spotify", "amazon", "apple", "tidal", "sonos"]

    def __init__(self) -> None:
        self.settings = get_settings()
        self._speakers: dict[str, soco.SoCo] = {}
        self._default_speaker: soco.SoCo | None = None

    def _discover_speakers(self) -> None:
        """Discover Sonos speakers on the network."""
        if self._speakers:
            return  # Already discovered

        try:
            speakers = list(soco.discover(timeout=5) or [])
            for speaker in speakers:
                name = speaker.player_name.lower()
                self._speakers[name] = speaker
                # Use first speaker as default if none set
                if self._default_speaker is None:
                    self._default_speaker = speaker
        except Exception:
            pass

    def _get_speaker(self, room: str | None = None) -> soco.SoCo | None:
        """Get a speaker by room name, or return default."""
        self._discover_speakers()

        if room:
            room_lower = room.lower().strip()
            # Try exact match
            if room_lower in self._speakers:
                return self._speakers[room_lower]
            # Try partial match
            for name, speaker in self._speakers.items():
                if room_lower in name or name in room_lower:
                    return speaker

        return self._default_speaker

    def _extract_room(self, query: str) -> str | None:
        """Extract room name from query."""
        query_lower = query.lower()

        # Look for "in/on the X room" pattern
        match = re.search(r"(?:in|on)\s+(?:the\s+)?(\w+(?:\s+\w+)?)\s*(?:room)?(?:\s+(?:speaker|on\s+sonos))?", query_lower)
        if match:
            room = match.group(1).strip()
            # Don't match service names as rooms
            if room not in ["pandora", "spotify", "amazon", "apple", "tidal", "sonos"]:
                return room
        return None

    def _extract_service(self, query: str) -> str | None:
        """Extract music service name from query."""
        query_lower = query.lower()
        for service in self.MUSIC_SERVICES:
            if service in query_lower and service != "sonos":
                return service
        return None

    def _clean_favorite_name(self, raw_name: str) -> str:
        """Clean up favorite name by removing room, service, and other modifiers."""
        name = raw_name.lower().strip()

        # Apply all strip patterns (may need multiple passes)
        for _ in range(2):
            for pattern in self.STRIP_PATTERNS:
                name = re.sub(pattern, "", name, flags=re.IGNORECASE)
            name = name.strip()

        # Remove leading "my" or "the"
        name = re.sub(r"^(?:my|the)\s+", "", name)

        # Remove trailing "on sonos" or room references that might remain
        name = re.sub(r"\s+on\s+sonos.*$", "", name)
        name = re.sub(r"\s+sonos\s+\w+.*$", "", name)  # "sonos dining room"

        return name.strip()

    async def match(self, query: str) -> SkillMatch:
        """Check if user wants to control Sonos."""
        query_lower = query.lower()

        # Check for various music control patterns
        room = self._extract_room(query)
        service = self._extract_service(query)

        # What's playing
        for pattern in self.WHATS_PLAYING_PATTERNS:
            if re.search(pattern, query_lower):
                return self._match(SkillConfidence.HIGH, action="whats_playing", room=room)

        # Pause/stop
        for pattern in self.PAUSE_PATTERNS:
            if re.search(pattern, query_lower):
                return self._match(SkillConfidence.HIGH, action="pause", room=room)

        # Skip/next
        for pattern in self.SKIP_PATTERNS:
            if re.search(pattern, query_lower):
                return self._match(SkillConfidence.HIGH, action="next", room=room)

        # Previous
        for pattern in self.PREVIOUS_PATTERNS:
            if re.search(pattern, query_lower):
                return self._match(SkillConfidence.HIGH, action="previous", room=room)

        # Volume control
        for pattern in self.VOLUME_PATTERNS:
            match = re.search(pattern, query_lower)
            if match:
                vol_arg = match.group(1) if match.lastindex else None
                return self._match(SkillConfidence.HIGH, action="volume", volume_arg=vol_arg, room=room)

        # Play favorite/playlist (check before generic play)
        for pattern in self.PLAY_FAVORITE_PATTERNS:
            match = re.search(pattern, query_lower)
            if match:
                raw_favorite = match.group(1).strip()
                # Clean up the favorite name
                favorite = self._clean_favorite_name(raw_favorite)
                # Don't match if it's just "play music" or similar
                if favorite and favorite not in ["music", "song", "songs", "something", "audio", ""]:
                    return self._match(SkillConfidence.HIGH, action="play_favorite", favorite=favorite, room=room, service=service)

        # Generic play
        for pattern in self.PLAY_PATTERNS:
            if re.search(pattern, query_lower):
                return self._match(SkillConfidence.HIGH, action="play", room=room)

        # Weak match for music-related keywords
        if any(word in query_lower for word in ["sonos", "speaker", "music"]):
            return self._match(SkillConfidence.LOW, action="help", room=room)

        return self._no_match()

    async def execute(self, query: str, extracted: dict[str, Any]) -> SkillResult:
        """Execute Sonos control."""
        action = extracted.get("action", "help")
        room = extracted.get("room")

        speaker = self._get_speaker(room)
        if not speaker:
            # Try discovery again
            self._speakers.clear()
            self._default_speaker = None
            speaker = self._get_speaker(room)

            if not speaker:
                return SkillResult.error(
                    "I couldn't find any Sonos speakers on your network. "
                    "Make sure they're powered on and connected."
                )

        try:
            if action == "play":
                return self._do_play(speaker)
            elif action == "pause":
                return self._do_pause(speaker)
            elif action == "next":
                return self._do_next(speaker)
            elif action == "previous":
                return self._do_previous(speaker)
            elif action == "volume":
                return self._do_volume(speaker, extracted.get("volume_arg"))
            elif action == "whats_playing":
                return self._do_whats_playing(speaker)
            elif action == "play_favorite":
                return self._do_play_favorite(speaker, extracted.get("favorite", ""), extracted.get("service"))
            else:
                return self._do_help(speaker)

        except SoCoException as e:
            return SkillResult.error(f"Sonos error: {str(e)}")
        except Exception as e:
            return SkillResult.error(f"Error controlling Sonos: {type(e).__name__}")

    def _do_play(self, speaker: soco.SoCo) -> SkillResult:
        """Resume playback."""
        speaker.play()
        return SkillResult.ok(
            f"Playing on {speaker.player_name}",
            speak=f"Playing on {speaker.player_name}",
        )

    def _do_pause(self, speaker: soco.SoCo) -> SkillResult:
        """Pause playback."""
        speaker.pause()
        return SkillResult.ok(
            f"Paused {speaker.player_name}",
            speak="Paused",
        )

    def _do_next(self, speaker: soco.SoCo) -> SkillResult:
        """Skip to next track."""
        speaker.next()
        return SkillResult.ok(
            "Skipping to next track",
            speak="Skipping",
        )

    def _do_previous(self, speaker: soco.SoCo) -> SkillResult:
        """Go to previous track."""
        speaker.previous()
        return SkillResult.ok(
            "Going to previous track",
            speak="Previous track",
        )

    def _do_volume(self, speaker: soco.SoCo, vol_arg: str | None) -> SkillResult:
        """Adjust volume."""
        current = speaker.volume

        if vol_arg is None:
            return SkillResult.ok(
                f"Volume on {speaker.player_name} is {current}%",
                speak=f"Volume is {current} percent",
            )

        vol_arg = vol_arg.lower()

        if vol_arg == "mute":
            speaker.mute = True
            return SkillResult.ok("Muted", speak="Muted")

        if vol_arg == "unmute":
            speaker.mute = False
            return SkillResult.ok("Unmuted", speak="Unmuted")

        if vol_arg in ("up", "louder"):
            new_vol = min(100, current + 10)
        elif vol_arg in ("down", "quieter", "softer"):
            new_vol = max(0, current - 10)
        else:
            # Try to parse as number
            try:
                new_vol = int(vol_arg)
                new_vol = max(0, min(100, new_vol))
            except ValueError:
                return SkillResult.error(f"I didn't understand the volume '{vol_arg}'")

        speaker.volume = new_vol
        return SkillResult.ok(
            f"Volume set to {new_vol}%",
            speak=f"Volume {new_vol} percent",
        )

    def _do_whats_playing(self, speaker: soco.SoCo) -> SkillResult:
        """Get current track info."""
        track = speaker.get_current_track_info()

        title = track.get("title", "Unknown")
        artist = track.get("artist", "Unknown")
        album = track.get("album", "")

        if title == "" or title == "Unknown":
            # Might be a radio station
            media = speaker.get_current_media_info()
            title = media.get("channel", "Unknown")
            artist = media.get("title", "")

        response = f"Now playing: {title}"
        if artist and artist != "Unknown":
            response += f" by {artist}"
        if album:
            response += f" ({album})"

        speak = f"Playing {title}"
        if artist and artist != "Unknown":
            speak += f" by {artist}"

        return SkillResult(
            success=True,
            response=response,
            speak=speak,
            data={"title": title, "artist": artist, "album": album},
        )

    def _do_play_favorite(self, speaker: soco.SoCo, favorite: str, service: str | None = None) -> SkillResult:
        """Play a Sonos favorite or search music service."""
        # If a service is specified and music services are available, try searching first
        if service and HAS_MUSIC_SERVICES:
            result = self._try_music_service(speaker, favorite, service)
            if result:
                return result

        # Fall back to Sonos favorites
        try:
            favorites = speaker.music_library.get_sonos_favorites()

            # Find matching favorite
            favorite_lower = favorite.lower()
            matched = None

            for fav in favorites:
                fav_title = fav.title.lower()
                if favorite_lower == fav_title:
                    matched = fav
                    break
                if favorite_lower in fav_title or fav_title in favorite_lower:
                    matched = fav

            if not matched:
                # List available favorites
                fav_names = [f.title for f in list(favorites)[:10]]
                hint = ""
                if service:
                    hint = f"\n\nTip: Add '{favorite}' to your Sonos favorites in the Sonos app to play it by voice."
                if fav_names:
                    return SkillResult.error(
                        f"I couldn't find '{favorite}'. Available favorites: {', '.join(fav_names)}{hint}"
                    )
                return SkillResult.error(
                    f"I couldn't find '{favorite}'. Add it to your Sonos favorites first.{hint}"
                )

            # Play the favorite - different methods for different content types
            # Radio stations and streams need play_uri, tracks can use queue
            try:
                # First try playing directly via URI (works for radio/streams)
                uri = matched.resources[0].uri if matched.resources else None
                if uri:
                    # For radio stations, use play_uri with metadata
                    meta = matched.to_didl_string() if hasattr(matched, 'to_didl_string') else None
                    speaker.play_uri(uri, meta=meta)
                else:
                    # Fallback to queue method for tracks
                    speaker.clear_queue()
                    speaker.add_to_queue(matched)
                    speaker.play_from_queue(0)
            except SoCoException:
                # If direct play fails, try queue method
                try:
                    speaker.clear_queue()
                    speaker.add_to_queue(matched)
                    speaker.play_from_queue(0)
                except SoCoException:
                    # Last resort: try play_uri without metadata
                    if matched.resources:
                        speaker.play_uri(matched.resources[0].uri)
                    else:
                        raise

            return SkillResult.ok(
                f"Playing {matched.title} on {speaker.player_name}",
                speak=f"Playing {matched.title}",
            )

        except SoCoException as e:
            return SkillResult.error(f"Couldn't play favorite: {str(e)}")

    def _try_music_service(self, speaker: soco.SoCo, search_term: str, service_name: str) -> SkillResult | None:
        """Try to search and play from a music service directly."""
        if not HAS_MUSIC_SERVICES:
            return None

        # Map common names to Sonos service names
        service_map = {
            "pandora": "Pandora",
            "spotify": "Spotify",
            "amazon": "Amazon Music",
            "apple": "Apple Music",
            "tidal": "TIDAL",
        }

        sonos_service_name = service_map.get(service_name.lower())
        if not sonos_service_name:
            return None

        try:
            # Check if service is available
            available = MusicService.get_all_music_services_names()
            if sonos_service_name not in available:
                return None

            service = MusicService(sonos_service_name)

            # Try to search for stations (for Pandora) or playlists
            search_categories = getattr(service, 'available_search_categories', [])

            result = None
            for category in ['stations', 'playlists', 'artists', 'tracks']:
                if category in search_categories:
                    try:
                        result = service.search(category=category, term=search_term)
                        if result:
                            break
                    except Exception:
                        continue

            if not result:
                return None

            # Get the first result
            items = list(result)
            if not items:
                return None

            item = items[0]

            # Get the URI and play it
            try:
                uri = service.sonos_uri_from_id(item.item_id)
                speaker.play_uri(uri)

                return SkillResult.ok(
                    f"Playing {item.title} from {sonos_service_name} on {speaker.player_name}",
                    speak=f"Playing {item.title}",
                )
            except Exception:
                # URI method failed, try adding to queue
                try:
                    speaker.clear_queue()
                    speaker.add_to_queue(item)
                    speaker.play_from_queue(0)

                    return SkillResult.ok(
                        f"Playing {item.title} from {sonos_service_name} on {speaker.player_name}",
                        speak=f"Playing {item.title}",
                    )
                except Exception:
                    return None

        except Exception:
            # Service not available or authentication issue
            return None

    def _do_help(self, speaker: soco.SoCo) -> SkillResult:
        """Show available commands."""
        speakers = ", ".join(self._speakers.keys()) if self._speakers else speaker.player_name
        return SkillResult.ok(
            f"I can control your Sonos speakers: {speakers}\n"
            "Try: play, pause, skip, volume up/down, what's playing, or play [favorite name]"
        )

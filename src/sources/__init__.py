# Expose fetchers here as instances in a dict for easy lookup.
from .genius_fetcher import GeniusFetcher
from .lrclib_fetcher import LRCLIBFetcher
from .simp_music_fetcher import SimpMusicFetcher
from .youtube_fetcher import YoutubeFetcher
from .lyricsovh_fetcher import LyricsOvhFetcher
from .chartlyrics_fetcher import ChartLyricsFetcher
from .lyricsfreek_fetcher import LyricsFreekFetcher

ALL_FETCHERS = {
    "genius": GeniusFetcher(),
    "lrclib": LRCLIBFetcher(),
    "simpmusic": SimpMusicFetcher(),
    "youtube": YoutubeFetcher(),
    "lyricsovh": LyricsOvhFetcher(),
    "chartlyrics": ChartLyricsFetcher(),
    "lyricsfreek": LyricsFreekFetcher(),
}

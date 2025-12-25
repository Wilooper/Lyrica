class BaseFetcher:
    """Abstract base fetcher class - implements common interface."""
    def fetch(self, artist: str, song: str, timestamps: bool=False):
        """
        Fetch lyrics.
        Return format (dict) similar to previous API:
          {
            "source": "genius",
            "artist": "...",
            "title": "...",
            "lyrics": "...",
            "timed_lyrics": [...],    # optional
            "hasTimestamps": True/False,
            "timestamp": "YYYY-MM-DD HH:MM:SS"
          }
        """
        raise NotImplementedError

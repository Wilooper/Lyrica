from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import json
from enum import Enum
import asyncio
import os
import requests
import logging

logger = logging.getLogger(__name__)

class Country(Enum):
    """Supported countries for trending data (ISO 3166-1 alpha-2 codes)"""
    US = "us"
    GB = "gb"
    IN = "in"
    BR = "br"
    JP = "jp"
    DE = "de"
    FR = "fr"
    CA = "ca"
    AU = "au"
    MX = "mx"

class TrendingSong:
    """Represents a trending song with metadata"""
    def __init__(self, 
                 song_id: str, 
                 title: str, 
                 artist: str,
                 rank: int,
                 plays: Optional[int] = None,
                 growth_rate: Optional[float] = None,
                 album: Optional[str] = None,
                 thumbnail: Optional[str] = None,
                 duration_seconds: Optional[int] = None,
                 explicit: bool = False,
                 genre: Optional[str] = None,
                 url: Optional[str] = None):
        self.song_id = song_id
        self.title = title
        self.artist = artist
        self.rank = rank
        self.plays = plays or 0
        self.growth_rate = growth_rate or 0.0
        self.album = album or "Unknown"
        self.thumbnail = thumbnail
        self.duration_seconds = duration_seconds
        self.explicit = explicit
        self.genre = genre
        self.url = url
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict:
        return {
            'song_id': self.song_id,
            'title': self.title,
            'artist': self.artist,
            'album': self.album,
            'rank': self.rank,
            'plays': self.plays,
            'growth_rate': self.growth_rate,
            'thumbnail': self.thumbnail,
            'duration_seconds': self.duration_seconds,
            'explicit': self.explicit,
            'genre': self.genre,
            'url': self.url,
            'timestamp': self.timestamp.isoformat()
        }

class UserQuery:
    """Represents a user query to Lyrica"""
    def __init__(self, user_id: str, query: str, country: str):
        self.user_id = user_id
        self.query = query
        self.country = country
        self.timestamp = datetime.now()
        self.query_normalized = query.lower().strip()
    
    def to_dict(self) -> Dict:
        return {
            'user_id': self.user_id,
            'query': self.query,
            'country': self.country,
            'timestamp': self.timestamp.isoformat()
        }

class TrendingAnalyticsEngine:
    """Main engine for handling trending songs and query analytics with Apple Music API"""
    
    def __init__(self, cache_ttl_hours: int = 6, request_timeout: int = 10):
        """
        Initialize the Trending Analytics Engine with Apple Music API
        
        Args:
            cache_ttl_hours: Cache time-to-live in hours (default 6 hours)
            request_timeout: HTTP request timeout in seconds
        """
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.request_timeout = request_timeout
        self.trending_cache = {}  # {country: (data, timestamp)}
        self.user_queries = []
        self.query_cache = defaultdict(int)  # {query: count}
        self.country_query_cache = defaultdict(lambda: defaultdict(int))  # {country: {query: count}}
        
        # Apple Music API Base URL
        self.apple_music_base_url = "https://rss.applemarketingtools.com/api/v2"
        
        logger.info("Trending Analytics Engine initialized with Apple Music API")
    
    def fetch_trending_songs(self, country: Country, limit: int = 50) -> List[TrendingSong]:
        """
        Fetch trending songs from Apple Music API for a specific country.
        
        Args:
            country: Country enum value
            limit: Number of trending songs to fetch (max 200)
        
        Returns:
            List of TrendingSong objects
        """
        if limit > 200:
            limit = 200
        if limit < 1:
            limit = 20
        
        # Check cache validity
        if self._is_cache_valid(country.value):
            logger.info(f"Using cached trending data for {country.value.upper()}")
            return self.trending_cache[country.value][0]
        
        try:
            logger.info(f"Fetching trending songs from Apple Music for {country.value.upper()}...")
            
            # Build Apple Music API URL
            api_url = f"{self.apple_music_base_url}/{country.value}/music/most-played/{limit}/songs.json"
            logger.debug(f"API URL: {api_url}")
            
            # Fetch data from Apple Music
            response = requests.get(api_url, timeout=self.request_timeout)
            response.raise_for_status()
            
            trending_data = response.json()
            
            if not trending_data:
                logger.warning(f"No trending data returned for {country.value.upper()}")
                return []
            
            # Debug logging
            logger.debug(f"Trending data type: {type(trending_data)}")
            if isinstance(trending_data, dict):
                logger.debug(f"Trending data keys: {list(trending_data.keys())}")
            
            # Parse and enrich data
            trending_songs = self._parse_trending_data(trending_data, country.value, limit)
            
            # Cache the results
            self.trending_cache[country.value] = (trending_songs, datetime.now())
            logger.info(f"Successfully cached {len(trending_songs)} trending songs for {country.value.upper()}")
            
            return trending_songs
        
        except requests.exceptions.Timeout:
            logger.error(f"Timeout fetching trending for {country.value.upper()}")
            if country.value in self.trending_cache:
                logger.info(f"Returning expired cache for {country.value.upper()}")
                return self.trending_cache[country.value][0]
            return []
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error fetching trending for {country.value.upper()}: {str(e)}")
            if country.value in self.trending_cache:
                logger.info(f"Returning expired cache for {country.value.upper()}")
                return self.trending_cache[country.value][0]
            return []
        
        except Exception as e:
            logger.error(f"Error fetching trending for {country.value.upper()}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            if country.value in self.trending_cache:
                logger.info(f"Returning expired cache for {country.value.upper()}")
                return self.trending_cache[country.value][0]
            return []
    
    def get_trending_by_countries(self, countries: List[Country], 
                                  limit: int = 50) -> Dict[str, List[TrendingSong]]:
        """
        Get trending songs across multiple countries.
        
        Args:
            countries: List of Country enums
            limit: Number of songs per country
        
        Returns:
            Dictionary mapping country codes to trending songs
        """
        results = {}
        for country in countries:
            try:
                results[country.value.upper()] = self.fetch_trending_songs(country, limit)
            except Exception as e:
                logger.error(f"Failed to fetch trending for {country.value.upper()}: {str(e)}")
                results[country.value.upper()] = []
        
        return results
    
    def record_user_query(self, user_id: str, query: str, country: str) -> None:
        """
        Record a user's query for analytics.
        
        Args:
            user_id: Unique user identifier
            query: The search query
            country: Country code (ISO 3166-1 alpha-2)
        """
        try:
            user_query = UserQuery(user_id, query, country.upper())
            self.user_queries.append(user_query)
            
            # Update global query cache
            self.query_cache[user_query.query_normalized] += 1
            
            # Update country-specific query cache
            self.country_query_cache[country.upper()][user_query.query_normalized] += 1
            
            logger.debug(f"Recorded query: {query} from user {user_id} in {country.upper()}")
        except Exception as e:
            logger.error(f"Error recording user query: {str(e)}")
    
    def get_top_queries(self, limit: int = 20, country: Optional[str] = None,
                       days: Optional[int] = None) -> List[Tuple[str, int]]:
        """
        Get top user queries globally or by country.
        
        Args:
            limit: Number of top queries to return
            country: Optional country filter
            days: Optional time window in days (None = all time)
        
        Returns:
            List of tuples: (query, count)
        """
        if limit < 1 or limit > 100:
            limit = 20
        
        if country:
            queries_to_analyze = self.country_query_cache.get(country.upper(), {}).copy()
        else:
            queries_to_analyze = self.query_cache.copy()
        
        # Filter by time window if specified
        if days:
            cutoff_date = datetime.now() - timedelta(days=days)
            queries_to_analyze = self._filter_queries_by_date(
                queries_to_analyze, cutoff_date
            )
        
        # Sort by frequency and return top N
        top_queries = sorted(queries_to_analyze.items(), key=lambda x: x[1], 
                            reverse=True)[:limit]
        
        logger.info(f"Retrieved {len(top_queries)} top queries (limit={limit}, country={country}, days={days})")
        return top_queries
    
    def get_top_queries_by_country(self, limit: int = 20) -> Dict[str, List[Tuple[str, int]]]:
        """
        Get top queries for each country.
        
        Args:
            limit: Number of top queries per country
        
        Returns:
            Dictionary mapping country codes to top queries
        """
        if limit < 1 or limit > 100:
            limit = 20
        
        results = {}
        for country in self.country_query_cache:
            results[country] = sorted(
                self.country_query_cache[country].items(),
                key=lambda x: x[1],
                reverse=True
            )[:limit]
        
        logger.info(f"Retrieved top queries by country (limit={limit}, countries={len(results)})")
        return results
    
    def get_trending_vs_user_queries(self, country: Country, limit: int = 10) -> Dict:
        """
        Compare trending songs with top user queries for insight.
        Shows what users are searching for vs what's trending.
        
        Args:
            country: Country to analyze
            limit: Number of items to return
        
        Returns:
            Dictionary with trending songs and top queries
        """
        trending = self.fetch_trending_songs(country, limit)
        top_queries = self.get_top_queries(limit, country.value.upper())
        
        # Extract trending titles and artists for comparison
        trending_info = [
            f"{song.title} - {song.artist}" 
            for song in trending
        ]
        
        logger.info(f"Generated trending vs queries comparison for {country.value.upper()}")
        
        return {
            'country': country.value.upper(),
            'trending_songs': [s.to_dict() for s in trending],
            'top_user_queries': [{'query': q, 'count': c} for q, c in top_queries],
            'trending_titles': trending_info
        }
    
    def get_trending_intersection(self, country: Country, limit: int = 10) -> List[Dict]:
        """
        Find queries that match trending songs (overlap analysis).
        
        Args:
            country: Country to analyze
            limit: Number of matches to return
        
        Returns:
            List of queries that match trending songs
        """
        trending = self.fetch_trending_songs(country, limit * 2)
        top_queries = self.get_top_queries(limit * 2, country.value.upper())
        
        # Build keyword index from trending songs
        trending_keywords = {}
        for song in trending:
            # Store multiple variations for better matching
            title_lower = song.title.lower()
            artist_lower = song.artist.lower()
            
            if title_lower not in trending_keywords:
                trending_keywords[title_lower] = song
            if artist_lower not in trending_keywords:
                trending_keywords[artist_lower] = song
            
            # Also store combined
            combined = f"{title_lower} {artist_lower}"
            if combined not in trending_keywords:
                trending_keywords[combined] = song
        
        # Match queries against trending
        matches = []
        seen_queries = set()
        
        for query, count in top_queries:
            query_lower = query.lower()
            
            # Skip if already matched
            if query_lower in seen_queries:
                continue
            
            # Check for matches
            for keyword, song in trending_keywords.items():
                if keyword in query_lower or query_lower in keyword:
                    matches.append({
                        'query': query,
                        'count': count,
                        'matched_song': song.title,
                        'matched_artist': song.artist,
                        'rank': song.rank
                    })
                    seen_queries.add(query_lower)
                    break
        
        logger.info(f"Found {len(matches)} intersection matches for {country.value.upper()}")
        return matches[:limit]
    
    def get_cache_status(self) -> Dict:
        """Get status of current cache"""
        cache_info = {
            'total_cached_countries': len(self.trending_cache),
            'cached_countries': [c.upper() for c in self.trending_cache.keys()],
            'total_recorded_queries': len(self.user_queries),
            'unique_global_queries': len(self.query_cache),
            'countries_with_queries': len(self.country_query_cache),
            'cache_ttl_hours': self.cache_ttl.total_seconds() / 3600,
            'cache_details': {}
        }
        
        for country, (data, timestamp) in self.trending_cache.items():
            age = datetime.now() - timestamp
            is_valid = age < self.cache_ttl
            cache_info['cache_details'][country.upper()] = {
                'cached_at': timestamp.isoformat(),
                'age_minutes': int(age.total_seconds() / 60),
                'is_valid': is_valid,
                'songs_count': len(data)
            }
        
        return cache_info
    
    def clear_cache(self) -> Dict:
        """Clear all caches"""
        try:
            countries_cleared = [c.upper() for c in self.trending_cache.keys()]
            self.trending_cache.clear()
            logger.info(f"Cleared cache for countries: {countries_cleared}")
            return {
                'status': 'success',
                'message': f'Cleared cache for {len(countries_cleared)} countries',
                'countries': countries_cleared
            }
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def _is_cache_valid(self, country: str) -> bool:
        """Check if cache is still valid"""
        if country not in self.trending_cache:
            return False
        _, timestamp = self.trending_cache[country]
        return datetime.now() - timestamp < self.cache_ttl
    
    def _parse_trending_data(self, raw_data: Dict, country: str, limit: int) -> List[TrendingSong]:
        """
        Parse Apple Music API trending data into TrendingSong objects.
        Validates and extracts all available metadata.
        """
        songs = []
        
        try:
            # Apple Music API structure: { "feed": { "results": [ songs ] } }
            items_to_process = []
            
            if isinstance(raw_data, dict):
                # Check for feed -> results structure
                if 'feed' in raw_data:
                    feed = raw_data['feed']
                    if isinstance(feed, dict) and 'results' in feed:
                        items_to_process = feed['results']
                # Check for direct results
                elif 'results' in raw_data:
                    items_to_process = raw_data['results']
                # Check for direct data array
                elif isinstance(raw_data, dict):
                    for key, value in raw_data.items():
                        if isinstance(value, list) and len(value) > 0:
                            items_to_process = value
                            break
            elif isinstance(raw_data, list):
                items_to_process = raw_data
            
            logger.debug(f"Processing {len(items_to_process)} items for {country.upper()}")
            
            for idx, item in enumerate(items_to_process[:limit]):
                try:
                    if not isinstance(item, dict):
                        logger.warning(f"Item #{idx} is not a dict, skipping")
                        continue
                    
                    # Extract basic info
                    song_id = item.get('id') or item.get('adamId') or f"song_{idx}"
                    
                    # Extract title
                    title = item.get('name') or item.get('title') or item.get('trackName', 'Unknown')
                    if not title or title == 'Unknown':
                        logger.debug(f"Skipping item #{idx}: no title found")
                        continue
                    
                    # Extract artist
                    artist = 'Unknown'
                    if 'artistName' in item:
                        artist = item['artistName']
                    elif 'artist' in item:
                        artist_data = item['artist']
                        if isinstance(artist_data, dict):
                            artist = artist_data.get('name', 'Unknown')
                        else:
                            artist = str(artist_data)
                    elif 'artists' in item:
                        artists = item['artists']
                        if isinstance(artists, list) and artists:
                            if isinstance(artists[0], dict):
                                artist = ', '.join([a.get('name', '') for a in artists if a.get('name')])
                            else:
                                artist = ', '.join([str(a) for a in artists])
                    
                    # Extract album
                    album = None
                    if 'albumName' in item:
                        album = item['albumName']
                    elif 'album' in item:
                        album_data = item['album']
                        if isinstance(album_data, dict):
                            album = album_data.get('name')
                        else:
                            album = album_data
                    
                    # Extract artwork/thumbnail
                    thumbnail = None
                    if 'artworkUrl100' in item:
                        thumbnail = item['artworkUrl100']
                    elif 'artwork' in item:
                        artwork = item['artwork']
                        if isinstance(artwork, dict):
                            thumbnail = artwork.get('url')
                        else:
                            thumbnail = artwork
                    
                    # Extract duration
                    duration = None
                    if 'durationMs' in item:
                        duration = int(item['durationMs'] / 1000)
                    elif 'duration' in item:
                        duration = item['duration']
                    
                    # Extract explicit flag
                    explicit = item.get('contentAdvisoryRating') == 'explicit' or item.get('isExplicit', False)
                    
                    # Extract genre
                    genre = None
                    if 'genres' in item:
                        genres = item['genres']
                        if isinstance(genres, list) and genres:
                            genre = genres[0].get('name') if isinstance(genres[0], dict) else genres[0]
                    elif 'genre' in item:
                        genre = item['genre']
                    
                    # Extract URL
                    url = item.get('url') or item.get('link')
                    
                    # Create song object
                    song = TrendingSong(
                        song_id=song_id,
                        title=title,
                        artist=artist,
                        rank=len(songs) + 1,
                        plays=0,
                        growth_rate=0.0,
                        album=album,
                        thumbnail=thumbnail,
                        duration_seconds=duration,
                        explicit=explicit,
                        genre=genre,
                        url=url
                    )
                    
                    songs.append(song)
                    logger.debug(f"Parsed trending song #{len(songs)}: {title} - {artist}")
                
                except Exception as e:
                    logger.warning(f"Error parsing item #{idx}: {str(e)}")
                    continue
            
            logger.info(f"Successfully parsed {len(songs)} trending songs for {country.upper()}")
            return songs
        
        except Exception as e:
            logger.error(f"Error parsing trending data: {str(e)}")
            logger.error(f"Raw data type: {type(raw_data)}")
            return []
    
    def _filter_queries_by_date(self, queries: Dict, cutoff_date: datetime) -> Dict:
        """Filter queries to only include those after cutoff date"""
        filtered = {}
        
        for query_obj in self.user_queries:
            if query_obj.timestamp >= cutoff_date:
                normalized = query_obj.query_normalized
                filtered[normalized] = filtered.get(normalized, 0) + 1
        
        logger.info(f"Filtered queries from {len(self.user_queries)} to {len(filtered)} after cutoff date")
        return filtered


# Example usage and testing
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Initialize engine
    engine = TrendingAnalyticsEngine()
    
    # Fetch trending for different countries
    print("\n=== Fetching Trending Songs from Apple Music ===")
    for country in [Country.US, Country.IN, Country.GB]:
        trending = engine.fetch_trending_songs(country, limit=5)
        print(f"\n{country.value.upper()} Trending ({len(trending)} songs):")
        for song in trending:
            print(f"  #{song.rank}: {song.title} - {song.artist}")
    
    # Simulate user queries
    print("\n=== Recording User Queries ===")
    sample_queries = [
        ("user123", "Taylor Swift", "US"),
        ("user456", "BTS", "IN"),
        ("user123", "Taylor Swift", "US"),
        ("user789", "The Weeknd", "GB"),
        ("user456", "BTS", "IN"),
    ]
    
    for user_id, query, country in sample_queries:
        engine.record_user_query(user_id, query, country)
        print(f"  Recorded: {query} ({country.upper()})")
    
    # Get top queries
    print("\n=== Top Queries ===")
    top_global = engine.get_top_queries(limit=5)
    print(f"Global top queries: {top_global}")
    
    # Get cache status
    print("\n=== Cache Status ===")
    cache_status = engine.get_cache_status()
    print(json.dumps(cache_status, indent=2))
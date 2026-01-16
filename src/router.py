from flask import jsonify, request, render_template
from datetime import datetime, timezone
import os

from src.logger import get_logger
from src.cache import make_cache_key, load_from_cache, save_to_cache, clear_cache, cache_stats
from src.fetch_controller import fetch_lyrics_controller
from src.sentiment_analyzer import analyze_sentiment, analyze_word_frequency, extract_lyrics_text
from src.metadata_extractor import enhance_lyrics_with_metadata, get_metadata_only
from src.sources.jiosaavan_fetcher import search_jiosaavn, get_jiosaavn_stream

logger = get_logger("router")



def register_routes(app):
    @app.route("/")
    def home():
        return jsonify(
            {
                "api": "Lyrica",
                "version": app.config.get("VERSION", "1.0.0"),  # Default version if not set
                "status": "active",
                "endpoints": {
                    "lyrics": "/lyrics/?artist=ARTIST&song=SONG",
                    "lyrics_synced": "/lyrics/?artist=ARTIST&song=SONG&timestamps=true",
                    "lyrics_fast": "/lyrics/?artist=ARTIST&song=SONG&fast=true",
                    "lyrics_with_mood": "/lyrics/?artist=ARTIST&song=SONG&mood=true",
                    "lyrics_with_metadata": "/lyrics/?artist=ARTIST&song=SONG&metadata=true",
                    "lyrics_all_features": "/lyrics/?artist=ARTIST&song=SONG&timestamps=true&fast=true&mood=true&metadata=true",
                    "metadata_only": "/metadata/?artist=ARTIST&song=SONG"
                },
                "parameters": {
                    "artist": "Required - Artist name",
                    "song": "Required - Song title",
                    "timestamps": "Optional - Get synced lyrics (true/false)",
                    "fast": "Optional - Use parallel fetching (true/false)",
                    "mood": "Optional - Analyze song mood/sentiment (true/false)",
                    "metadata": "Optional - Include song metadata (true/false, default: false)",
                    "pass": "Optional - Custom fetcher sequence (true/false)",
                    "sequence": "Optional with pass=true - Comma-separated fetcher IDs (1-6)"
                },
                "fetchers": {
                    "1": "Genius",
                    "2": "LRCLIB",
                    "3": "SimpMusic",
                    "4": "YouTube Music",
                    "5": "Lyrics.ovh",
                    "6": "ChartLyrics"
                },
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    @app.route("/lyrics/", methods=["GET"])
    async def lyrics():
        artist = request.args.get("artist", "").strip()
        song = request.args.get("song", "").strip()
        timestamps = (
            request.args.get("timestamps", "false").lower() == "true"
            or request.args.get("timestamp", "false").lower() == "true"
        )
        pass_param = request.args.get("pass", "false").lower() == "true"
        sequence = request.args.get("sequence", None)
        fast_mode = request.args.get("fast", "false").lower() == "true"
        analyze_mood = request.args.get("mood", "false").lower() == "true"
        include_metadata = request.args.get("metadata", "false").lower() == "true"  # Added handling for metadata param

        if not artist or not song:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Artist and song name are required",
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    },
                }),
                400,
            )

        if pass_param and not sequence:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Sequence parameter is required when pass=true",
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    },
                }),
                400,
            )

        logger.info(f"Lyrics request: {artist} - {song} (fast={fast_mode}, mood={analyze_mood}, metadata={include_metadata})")
        
        # 1. Check Cache First
        cache_key = make_cache_key(artist, song, timestamps, sequence)
        cached = load_from_cache(cache_key)

        if cached:
            logger.info(f"Cache hit for {artist} - {song}")
            result = cached
        else:
            # 2. Fetch Fresh Data
            result = await fetch_lyrics_controller(
                artist, song, 
                timestamps=timestamps, 
                pass_param=pass_param, 
                sequence=sequence,
                fast_mode=fast_mode
            )

            # 3. Cache if successful
            if result.get("status") == "success":
                data = result.get("data", {})
                if data.get("lyrics") or data.get("plain_lyrics") or data.get("lyrics_text"):
                    save_to_cache(cache_key, result)
                else:
                    logger.warning(f"Fetch successful but no lyrics content found for {artist} - {song}. Skipping cache.")

        # 4. Analyze mood if requested
        if analyze_mood and result.get("status") == "success":
            data = result.get("data", {})
            lyrics_text = extract_lyrics_text(data)
            
            if lyrics_text:
                sentiment = analyze_sentiment(lyrics_text)
                word_freq = analyze_word_frequency(lyrics_text, top_n=5)
                
                result["mood_analysis"] = {
                    "sentiment": sentiment,
                    "top_words": word_freq
                }
                logger.info(f"Mood analysis: {sentiment['mood']}")
            else:
                logger.warning("Could not extract lyrics for mood analysis")
                result["mood_analysis"] = {"error": "Unable to extract lyrics for analysis"}

        # 5. Include metadata if requested
        if include_metadata and result.get("status") == "success":
            result = enhance_lyrics_with_metadata(result, artist, song)
            logger.info(f"Metadata enhanced for {artist} - {song}")

        return jsonify(result)

    @app.route("/api/search", methods=["GET"])
    def music_search():
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"status": "error", "error": {"message": "Query parameter 'q' is required"}}), 400

        results = fetch_music_search(query)
        return jsonify({"status": "success", "results": results})

    
    @app.route("/api/jiosaavn/search", methods=["GET"])
    def jiosaavn_search():
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"status": "error", "error": {"message": "Query parameter 'q' is required"}}), 400

        results = search_jiosaavn(query)
        return jsonify({"status": "success", "results": results})

    @app.route("/api/jiosaavn/play", methods=["GET"])
    def jiosaavn_play():
        song_link = request.args.get("songLink", "").strip()
        if not song_link:
            return jsonify({"status": "error", "error": {"message": "songLink is required"}}), 400

        data = get_jiosaavn_stream(song_link)
        if not data.get("stream_url"):
            return jsonify({"status": "error", "error": {"message": "Unable to fetch stream"}}), 500

        return jsonify({"status": "success", "data": data})

    @app.route("/app")
    def app_page():
        try:
            return render_template("index.html")
        except Exception:
            return "", 204

    @app.route("/cache/clear", methods=["POST"])
    def route_clear_cache():
        res = clear_cache()
        return jsonify({"status": "success", "details": res})

    @app.route("/cache/stats", methods=["GET"])
    def route_cache_stats():
        stats = cache_stats()
        return jsonify({"status": "success", **stats})

    @app.route("/metadata/", methods=["GET"])
    def metadata():
        """Get song metadata only (without lyrics)"""
        artist = request.args.get("artist", "").strip()
        song = request.args.get("song", "").strip()
        
        if not artist or not song:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Artist and song name are required",
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    },
                }),
                400,
            )
        
        logger.info(f"Metadata request for {artist} - {song}")
        result = get_metadata_only(artist, song)
        
        return jsonify(result)

    @app.route("/favicon.ico")
    def favicon():
        return "", 204

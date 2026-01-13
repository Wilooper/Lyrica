from flask import jsonify, request, render_template
from datetime import datetime, timezone
import os

from src.logger import get_logger
from src.cache import make_cache_key, load_from_cache, save_to_cache, clear_cache, cache_stats
from src.fetch_controller import (
    fetch_lyrics_controller
)
from src.sources.jiosaavan_fetcher import search_jiosaavn, get_jiosaavn_stream

logger = get_logger("router")

def register_routes(app):
    @app.route("/")
    def home():
        return jsonify(
            {
                "api": "Lyrica",
                "version": app.config.get("VERSION"),
                "status": "active",
                "endpoints": {
                    "lyrics": "/lyrics/?artist=ARTIST&song=SONG&timestamps=true&pass=false&sequence=1,2,3"
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

        logger.info(f"Lyrics request received for {artist} - {song}")
        
        # 1. Check Cache First
        cache_key = make_cache_key(artist, song, timestamps, sequence)
        cached = load_from_cache(cache_key)

        if cached:
            logger.info(f"Cache hit for {artist} - {song}")
            return jsonify(cached)

        # 2. Fetch Fresh Data
        result = await fetch_lyrics_controller(
            artist, song, timestamps=timestamps, pass_param=pass_param, sequence=sequence
        )

        # 3. IMPROVED CACHE LOGIC: Only cache if lyrics are actually present
        if result.get("status") == "success":
            data = result.get("data", {})
            # Validate that there is actual text in lyrics or plain_lyrics
            if data.get("lyrics") or data.get("plain_lyrics") or data.get("lyrics_text"):
                save_to_cache(cache_key, result)
            else:
                logger.warning(f"Fetch successful but no lyrics content found for {artist} - {song}. Skipping cache.")

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

    @app.route("/favicon.ico")
    def favicon():
        return "", 204


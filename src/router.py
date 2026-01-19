from flask import jsonify, request, render_template
from datetime import datetime, timezone
import os
import asyncio
import logging

from src.logger import get_logger
from src.cache import make_cache_key, load_from_cache, save_to_cache, clear_cache, cache_stats
from src.fetch_controller import fetch_lyrics_controller
from src.sentiment_analyzer import analyze_sentiment, analyze_word_frequency, extract_lyrics_text
from src.metadata_extractor import enhance_lyrics_with_metadata, get_metadata_only
from src.sources.jiosaavan_fetcher import search_jiosaavn, get_jiosaavn_stream
from src.trending_analytics import TrendingAnalyticsEngine, Country

logger = get_logger("router")

# Initialize Trending Analytics Engine (global instance)
trending_engine = TrendingAnalyticsEngine(cache_ttl_hours=24)

# Helper function to run async functions in sync context
def run_async(coro, timeout=30):
    """Run async coroutine safely in sync context with timeout"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.run(coro)
        return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
    except asyncio.TimeoutError:
        logger.error("Async operation timed out")
        raise Exception("Request timed out - operation took too long")
    except RuntimeError:
        return asyncio.run(asyncio.wait_for(coro, timeout=timeout))


def register_routes(app):
    @app.route("/")
    def home():
        """Main API documentation endpoint"""
        return jsonify(
            {
                "api": "Lyrica",
                "version": app.config.get("VERSION", "1.0.0"),
                "status": "active",
                "description": "A comprehensive lyrics API with mood analysis, metadata extraction, and trending insights",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "endpoints": {
                    "lyrics": {
                        "url": "/lyrics/",
                        "method": "GET",
                        "description": "Fetch lyrics for a song",
                        "examples": [
                            "/lyrics/?artist=The Beatles&song=Imagine",
                            "/lyrics/?artist=The Beatles&song=Imagine&timestamps=true",
                            "/lyrics/?artist=The Beatles&song=Imagine&mood=true",
                            "/lyrics/?artist=The Beatles&song=Imagine&metadata=true",
                            "/lyrics/?artist=The Beatles&song=Imagine&fast=true&timestamps=true&mood=true&metadata=true"
                        ]
                    },
                    "metadata_only": {
                        "url": "/metadata/",
                        "method": "GET",
                        "description": "Get song metadata without lyrics",
                        "examples": [
                            "/metadata/?artist=The Beatles&song=Imagine"
                        ]
                    },
                    "trending": {
                        "url": "/trending/",
                        "method": "GET",
                        "description": "Get trending songs by country",
                        "examples": [
                            "/trending/?country=US&limit=20",
                            "/trending/?country=IN",
                            "/trending/?countries=US,GB,IN&limit=10"
                        ]
                    },
                    "top_queries": {
                        "url": "/analytics/top-queries/",
                        "method": "GET",
                        "description": "Get top user queries globally or by country",
                        "examples": [
                            "/analytics/top-queries/?limit=20",
                            "/analytics/top-queries/?country=US&limit=10",
                            "/analytics/top-queries/?country=US&days=7&limit=15"
                        ]
                    },
                    "trending_by_country": {
                        "url": "/analytics/trending-by-country/",
                        "method": "GET",
                        "description": "Get top queries for each country",
                        "examples": [
                            "/analytics/trending-by-country/?limit=10"
                        ]
                    },
                    "trending_vs_queries": {
                        "url": "/analytics/trending-vs-queries/",
                        "method": "GET",
                        "description": "Compare trending songs with top user queries",
                        "examples": [
                            "/analytics/trending-vs-queries/?country=US&limit=10"
                        ]
                    },
                    "trending_intersection": {
                        "url": "/analytics/trending-intersection/",
                        "method": "GET",
                        "description": "Find queries that match trending songs",
                        "examples": [
                            "/analytics/trending-intersection/?country=US&limit=10"
                        ]
                    },
                    "jiosaavn_search": {
                        "url": "/api/jiosaavn/search",
                        "method": "GET",
                        "description": "Search for songs on JioSaavn",
                        "examples": [
                            "/api/jiosaavn/search?q=Imagine"
                        ]
                    },
                    "jiosaavn_play": {
                        "url": "/api/jiosaavn/play",
                        "method": "GET",
                        "description": "Get playable stream URL from JioSaavn",
                        "examples": [
                            "/api/jiosaavn/play?songLink=<song_link>"
                        ]
                    },
                    "cache_stats": {
                        "url": "/cache/stats",
                        "method": "GET",
                        "description": "Get cache statistics"
                    },
                    "music_app": {
                        "url": "/app",
                        "method": "GET",
                        "description": "Access the web-based music application"
                    }
                },
                "parameters": {
                    "artist": {
                        "type": "string",
                        "required": True,
                        "description": "Artist name"
                    },
                    "song": {
                        "type": "string",
                        "required": True,
                        "description": "Song title"
                    },
                    "country": {
                        "type": "string",
                        "required": False,
                        "description": "Country code (US, GB, IN, BR, JP, DE, FR, CA, AU, MX)"
                    },
                    "countries": {
                        "type": "string",
                        "required": False,
                        "description": "Comma-separated country codes"
                    },
                    "limit": {
                        "type": "integer",
                        "required": False,
                        "default": 20,
                        "description": "Number of results to return"
                    },
                    "days": {
                        "type": "integer",
                        "required": False,
                        "description": "Time window in days for query analytics"
                    },
                    "timestamps": {
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Include synchronized timestamps with lyrics"
                    },
                    "mood": {
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Analyze song mood/sentiment and top words"
                    },
                    "metadata": {
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Include song metadata (cover art, duration, genre, etc.)"
                    },
                    "fast": {
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Use parallel fetching for faster results"
                    }
                },
                "fetchers": {
                    "1": "Genius",
                    "2": "LRCLIB",
                    "3": "SimpMusic",
                    "4": "YouTube Music",
                    "5": "Lyrics.ovh",
                    "6": "ChartLyrics"
                }
            }
        )

    @app.route("/lyrics/", methods=["GET"])
    def lyrics():
        """Fetch lyrics with optional mood analysis and metadata"""
        artist = request.args.get("artist", "").strip()
        song = request.args.get("song", "").strip()
        country = request.args.get("country", "US").strip().upper()
        timestamps = (
            request.args.get("timestamps", "false").lower() == "true"
            or request.args.get("timestamp", "false").lower() == "true"
        )
        pass_param = request.args.get("pass", "false").lower() == "true"
        sequence = request.args.get("sequence", None)
        fast_mode = request.args.get("fast", "false").lower() == "true"
        analyze_mood = request.args.get("mood", "false").lower() == "true"
        include_metadata = request.args.get("metadata", "false").lower() == "true"

        if not artist or not song:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Artist and song name are required",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
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
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                400,
            )

        logger.info(
            f"Lyrics request: {artist} - {song} (fast={fast_mode}, mood={analyze_mood}, metadata={include_metadata})"
        )

        # Record user query for analytics
        try:
            trending_engine.record_user_query(
                user_id=request.remote_addr,
                query=f"{artist} - {song}",
                country=country
            )
        except Exception as e:
            logger.warning(f"Failed to record user query: {str(e)}")

        # 1. Check Cache First
        cache_key = make_cache_key(artist, song, timestamps, sequence, fast_mode, analyze_mood, include_metadata)
        cached = load_from_cache(cache_key)

        if cached:
            logger.info(f"Cache hit for {artist} - {song}")
            return jsonify(cached)

        # 2. Fetch Fresh Data
        try:
            result = run_async(
                fetch_lyrics_controller(
                    artist,
                    song,
                    timestamps=timestamps,
                    pass_param=pass_param,
                    sequence=sequence,
                    fast_mode=fast_mode,
                ),
                timeout=60
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching lyrics for {artist} - {song}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Request timed out",
                        "details": "Lyrics fetch took too long",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                504,
            )
        except Exception as e:
            logger.error(f"Error fetching lyrics: {str(e)}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Failed to fetch lyrics",
                        "details": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                500,
            )

        if not isinstance(result, dict):
            logger.error(f"Invalid result type from fetch_lyrics_controller: {type(result)}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Invalid response from lyrics fetcher",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                500,
            )

        # 3. Analyze mood if requested
        if analyze_mood and result.get("status") == "success":
            data = result.get("data", {})
            lyrics_text = extract_lyrics_text(data)

            if lyrics_text:
                try:
                    sentiment = analyze_sentiment(lyrics_text)
                    word_freq = analyze_word_frequency(lyrics_text, top_n=5)

                    result["mood_analysis"] = {
                        "sentiment": sentiment,
                        "top_words": word_freq,
                    }
                    logger.info(f"Mood analysis completed for {artist} - {song}")
                except Exception as e:
                    logger.warning(f"Mood analysis failed: {str(e)}")
                    result["mood_analysis"] = {
                        "error": "Unable to perform mood analysis",
                        "details": str(e),
                    }
            else:
                logger.warning("Could not extract lyrics for mood analysis")
                result["mood_analysis"] = {"error": "Unable to extract lyrics for analysis"}

        # 4. Include metadata if requested
        if include_metadata and result.get("status") == "success":
            try:
                metadata_result = enhance_lyrics_with_metadata(result, artist, song)
                if asyncio.iscoroutine(metadata_result):
                    metadata_result = run_async(metadata_result, timeout=30)
                result = metadata_result
                logger.info(f"Metadata enhanced for {artist} - {song}")
            except Exception as e:
                logger.warning(f"Metadata enhancement failed: {str(e)}")
                result["metadata_error"] = f"Could not retrieve metadata: {str(e)}"

        # 5. Cache if successful
        if result.get("status") == "success":
            data = result.get("data", {})
            if data.get("lyrics") or data.get("plain_lyrics") or data.get("lyrics_text"):
                try:
                    save_to_cache(cache_key, result)
                    logger.info(f"Result cached for {artist} - {song}")
                except Exception as e:
                    logger.warning(f"Cache save failed: {str(e)}")
            else:
                logger.warning(
                    f"Fetch successful but no lyrics content found for {artist} - {song}. Skipping cache."
                )

        return jsonify(result)

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
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                400,
            )

        logger.info(f"Metadata request for {artist} - {song}")
        
        try:
            result = get_metadata_only(artist, song)
            if asyncio.iscoroutine(result):
                result = run_async(result, timeout=30)
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching metadata for {artist} - {song}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Request timed out",
                        "details": "Metadata fetch took too long",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                504,
            )
        except Exception as e:
            logger.error(f"Metadata fetch error: {str(e)}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Failed to fetch metadata",
                        "details": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                500,
            )

        return jsonify(result)

    @app.route("/trending/", methods=["GET"])
    def trending():
        """Get trending songs by country"""
        country = request.args.get("country", "US").strip().upper()
        countries_param = request.args.get("countries", "").strip()
        limit = request.args.get("limit", 20, type=int)

        if limit < 1 or limit > 100:
            limit = 20

        logger.info(f"Trending request: country={country}, limit={limit}")

        try:
            # Handle single country
            if country and not countries_param:
                try:
                    country_enum = Country[country]
                    trending_songs = trending_engine.fetch_trending_songs(country_enum, limit)
                    
                    return jsonify({
                        "status": "success",
                        "data": {
                            "country": country,
                            "trending": [song.to_dict() for song in trending_songs],
                            "total": len(trending_songs),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    })
                except KeyError:
                    return jsonify({
                        "status": "error",
                        "error": {
                            "message": f"Invalid country code: {country}",
                            "valid_countries": [c.value for c in Country],
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    }), 400

            # Handle multiple countries
            elif countries_param:
                country_list = [c.strip().upper() for c in countries_param.split(",")]
                trending_data = {}
                
                for c in country_list:
                    try:
                        country_enum = Country[c]
                        trending_songs = trending_engine.fetch_trending_songs(country_enum, limit)
                        trending_data[c] = [song.to_dict() for song in trending_songs]
                    except KeyError:
                        logger.warning(f"Invalid country code: {c}")
                        continue

                return jsonify({
                    "status": "success",
                    "data": {
                        "countries": trending_data,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                })

        except Exception as e:
            logger.error(f"Trending fetch error: {str(e)}")
            return jsonify({
                "status": "error",
                "error": {
                    "message": "Failed to fetch trending data",
                    "details": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 500

    @app.route("/analytics/top-queries/", methods=["GET"])
    def top_queries():
        """Get top user queries globally or by country"""
        limit = request.args.get("limit", 20, type=int)
        country = request.args.get("country", "").strip().upper()
        days = request.args.get("days", None, type=int)

        if limit < 1 or limit > 100:
            limit = 20

        logger.info(f"Top queries request: limit={limit}, country={country}, days={days}")

        try:
            top_q = trending_engine.get_top_queries(
                limit=limit,
                country=country if country else None,
                days=days
            )

            return jsonify({
                "status": "success",
                "data": {
                    "scope": "global" if not country else f"country_{country}",
                    "time_window": f"{days} days" if days else "all_time",
                    "top_queries": [{"query": q, "count": c} for q, c in top_q],
                    "total_unique": len(top_q),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            })

        except Exception as e:
            logger.error(f"Top queries fetch error: {str(e)}")
            return jsonify({
                "status": "error",
                "error": {
                    "message": "Failed to fetch top queries",
                    "details": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 500

    @app.route("/analytics/trending-by-country/", methods=["GET"])
    def trending_by_country():
        """Get top queries for each country"""
        limit = request.args.get("limit", 10, type=int)

        if limit < 1 or limit > 100:
            limit = 10

        logger.info(f"Trending by country request: limit={limit}")

        try:
            top_by_country = trending_engine.get_top_queries_by_country(limit=limit)

            return jsonify({
                "status": "success",
                "data": {
                    "countries": {
                        country: [{"query": q, "count": c} for q, c in queries]
                        for country, queries in top_by_country.items()
                    },
                    "total_countries": len(top_by_country),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            })

        except Exception as e:
            logger.error(f"Trending by country error: {str(e)}")
            return jsonify({
                "status": "error",
                "error": {
                    "message": "Failed to fetch trending by country",
                    "details": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 500

    @app.route("/analytics/trending-vs-queries/", methods=["GET"])
    def trending_vs_queries():
        """Compare trending songs with top user queries"""
        country = request.args.get("country", "US").strip().upper()
        limit = request.args.get("limit", 10, type=int)

        if limit < 1 or limit > 100:
            limit = 10

        logger.info(f"Trending vs queries request: country={country}, limit={limit}")

        try:
            country_enum = Country[country]
            comparison = trending_engine.get_trending_vs_user_queries(country_enum, limit)

            return jsonify({
                "status": "success",
                "data": comparison
            })

        except KeyError:
            return jsonify({
                "status": "error",
                "error": {
                    "message": f"Invalid country code: {country}",
                    "valid_countries": [c.value for c in Country],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 400
        except Exception as e:
            logger.error(f"Trending vs queries error: {str(e)}")
            return jsonify({
                "status": "error",
                "error": {
                    "message": "Failed to fetch trending vs queries",
                    "details": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 500

    @app.route("/analytics/trending-intersection/", methods=["GET"])
    def trending_intersection():
        """Find queries that match trending songs"""
        country = request.args.get("country", "US").strip().upper()
        limit = request.args.get("limit", 10, type=int)

        if limit < 1 or limit > 100:
            limit = 10

        logger.info(f"Trending intersection request: country={country}, limit={limit}")

        try:
            country_enum = Country[country]
            matches = trending_engine.get_trending_intersection(country_enum, limit)

            return jsonify({
                "status": "success",
                "data": {
                    "country": country,
                    "matches": matches,
                    "total_matches": len(matches),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            })

        except KeyError:
            return jsonify({
                "status": "error",
                "error": {
                    "message": f"Invalid country code: {country}",
                    "valid_countries": [c.value for c in Country],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 400
        except Exception as e:
            logger.error(f"Trending intersection error: {str(e)}")
            return jsonify({
                "status": "error",
                "error": {
                    "message": "Failed to fetch trending intersection",
                    "details": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 500

    @app.route("/api/jiosaavn/search", methods=["GET"])
    def jiosaavn_search():
        """Search for songs on JioSaavn"""
        query = request.args.get("q", "").strip()
        
        if not query:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Query parameter 'q' is required",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                400,
            )

        logger.info(f"JioSaavn search query: {query}")
        
        try:
            results = search_jiosaavn(query)
            if asyncio.iscoroutine(results):
                results = run_async(results, timeout=30)
            return jsonify({"status": "success", "results": results})
        except asyncio.TimeoutError:
            logger.error(f"Timeout searching JioSaavn for: {query}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Request timed out",
                        "details": "JioSaavn search took too long",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                504,
            )
        except Exception as e:
            logger.error(f"JioSaavn search error: {str(e)}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Failed to search JioSaavn",
                        "details": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                500,
            )

    @app.route("/api/jiosaavn/play", methods=["GET"])
    def jiosaavn_play():
        """Get playable stream URL from JioSaavn"""
        song_link = request.args.get("songLink", "").strip()
        
        if not song_link:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "songLink parameter is required",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                400,
            )

        logger.info(f"JioSaavn play request for: {song_link}")
        
        try:
            data = get_jiosaavn_stream(song_link)
            if asyncio.iscoroutine(data):
                data = run_async(data, timeout=30)
            
            if not data or not isinstance(data, dict):
                return (
                    jsonify({
                        "status": "error",
                        "error": {
                            "message": "Invalid response from JioSaavn",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    }),
                    500,
                )

            if not data.get("stream_url"):
                return (
                    jsonify({
                        "status": "error",
                        "error": {
                            "message": "Unable to fetch stream URL",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    }),
                    500,
                )

            return jsonify({"status": "success", "data": data})
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching stream for: {song_link}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Request timed out",
                        "details": "Stream fetch took too long",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                504,
            )
        except Exception as e:
            logger.error(f"JioSaavn play error: {str(e)}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Failed to fetch stream",
                        "details": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                500,
            )

    @app.route("/app", methods=["GET"])
    def app_page():
        """Serve the web-based music application"""
        try:
            return render_template("index.html")
        except Exception as e:
            logger.error(f"Failed to render app page: {str(e)}")
            return jsonify({
                "status": "error",
                "error": {
                    "message": "Failed to load application",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }), 500

    @app.route("/cache/stats", methods=["GET"])
    def route_cache_stats():
        """Get cache statistics and information"""
        try:
            stats = cache_stats()
            return jsonify({"status": "success", **stats})
        except Exception as e:
            logger.error(f"Cache stats error: {str(e)}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Failed to retrieve cache stats",
                        "details": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                500,
            )

    @app.route("/cache/clear", methods=["POST"])
    def route_clear_cache():
        """Clear all cached data (Admin only)"""
        try:
            res = clear_cache()
            logger.info("Cache cleared")
            return jsonify({"status": "success", "details": res})
        except Exception as e:
            logger.error(f"Cache clear error: {str(e)}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Failed to clear cache",
                        "details": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                500,
            )

    @app.route("/favicon.ico", methods=["GET"])
    def favicon():
        """Favicon endpoint"""
        return "", 204

    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 errors"""
        return (
            jsonify({
                "status": "error",
                "error": {
                    "message": "Endpoint not found",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }),
            404,
        )

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors"""
        logger.error(f"Internal server error: {str(error)}")
        return (
            jsonify({
                "status": "error",
                "error": {
                    "message": "Internal server error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }),
            500,
        )

'''
 @app.route("/debug/trending-raw", methods=["GET"])
def debug_trending_raw():
    """Debug endpoint to see raw trending data"""
    from src.trending_analytics import trending_engine, Country
    raw = trending_engine.ytmusic.get_trending(region="US")
    return jsonify({
        "type": str(type(raw)),
        "keys": list(raw.keys()) if isinstance(raw, dict) else "is_list",
        "first_item": raw[0] if isinstance(raw, list) and raw else (list(raw.items())[0] if isinstance(raw, dict) else None)
    })
'''
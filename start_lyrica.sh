#!/bin/bash

echo "🎵 Starting Lyrica Music Site..."
echo "================================"

# Check if Python dependencies are installed
echo "✅ Checking dependencies..."
python3 -c "import flask, flask_cors, ytmusicapi, lyricsgenius, requests, bs4" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ Missing dependencies. Installing..."
    pip install --break-system-packages -r requirements.txt
fi

# Start the Flask API server
echo "🚀 Starting Lyrica API server on port 9999..."
echo "📡 API will be available at: http://127.0.0.1:9999"
echo "🌐 GOTO http://127.0.0.1:9999/app in your browser to use the web interface"
echo "⭐ Try some sample searches:"
echo "   - Artist: Arijit Singh, Song: Tum Hi Ho"
echo "   - Artist: Yo Yo Honey Singh, Song: Blue Eyes (with timestamps for karaoke)"
echo ""
echo "TO USE INBUILT GUI GO TO:
http://127.0.0.1:9999/app"
echo ""
echo "💡 To stop the server, press Ctrl+C"
echo ""
echo "MADE BY WILOOPER WITH ❤️ "
echo "================================"

# Run the server
python3 lyrica.py

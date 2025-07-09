# 🎵 Lyrica Music Site - Complete Setup Guide

Welcome to your beautiful, modern music site! This guide will help you get everything running perfectly.

## 🚀 Quick Start

### 1. Start the Server
```bash
# Option 1: Use the startup script (recommended)
./start_lyrica.sh

# Option 2: Start manually
python3 lyrica.py
```

### 2. Open the Website
Open `index.html` in your web browser:
- **File path**: `file:///path/to/your/workspace/index.html`
- **Or double-click**: `index.html` file in your file manager

## 🎯 How to Use Your Music Site

### Basic Search
1. Enter an **Artist name** (e.g., "Arijit Singh")
2. Enter a **Song title** (e.g., "Tum Hi Ho")
3. Click **"Find Lyrics"**

### Karaoke Mode (Timestamped Lyrics)
1. Check the **"Get timestamped lyrics"** box
2. Search for a song
3. If timestamped lyrics are available, click **"Start Karaoke Mode"**
4. Enjoy synchronized lyrics highlighting!

## 🎪 Try These Sample Songs

| Artist | Song | Features |
|--------|------|----------|
| Arijit Singh | Tum Hi Ho | ⭐ Popular Bollywood hit |
| Yo Yo Honey Singh | Blue Eyes | 🎤 Great for karaoke mode |
| Rahat Fateh Ali Khan | Jag Ghoomeya | 🎵 Beautiful melody |
| Shreya Ghoshal | Teri Ore | 💫 Synchronized lyrics |

## 🔧 Configuration

### Set Genius API Token (Optional but Recommended)
```bash
export GENIUS_TOKEN="your_genius_api_key_here"
```
Get your free token at: https://genius.com/api-clients

### YouTube Music Setup (Optional)
For better YouTube Music results:
```bash
ytmusicapi setup
```
Follow the prompts to create `headers_auth.json`

## 🌐 API Endpoints

Your API is running at `http://127.0.0.1:9999`

### Get Lyrics
```
GET /lyrics/?artist=ARTIST&song=SONG&timestamps=true
```

**Example:**
```
http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&timestamps=true
```

### Check API Status
```
GET /
```

## 📱 Features Overview

- ✨ **Modern UI Design** - Beautiful gradient interface
- 🎤 **Karaoke Mode** - Real-time lyrics highlighting
- 📱 **Responsive** - Works on all devices
- 🌐 **Multi-Source** - 6 different lyrics sources
- ⚡ **Fast Search** - Instant results
- 🇮🇳 **Made in India** - With pride!

## 🎵 Supported Sources

1. **YouTube Music** - Primary source with timestamps
2. **LrcLib** - Synchronized LRC lyrics
3. **Genius** - Rich lyrics with artist verification
4. **Lyrics.ovh** - Fast and reliable
5. **ChartLyrics** - XML-based lyrics
6. **LyricsFreek** - Broad coverage

## 🐛 Troubleshooting

### API Not Working?
```bash
# Check if server is running
curl http://127.0.0.1:9999/

# Restart the server
pkill -f lyrica.py
python3 lyrica.py
```

### Missing Dependencies?
```bash
pip install --break-system-packages -r requirements.txt
```

### CORS Issues?
The API includes CORS headers, but if you face issues:
- Use a local server: `python3 -m http.server 8000`
- Or use a browser with disabled security for testing

## 🎨 Customization

### Change Colors/Theme
Edit `styles.css` - look for the gradient backgrounds:
```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```

### Add More Features
- Edit `script.js` to add new functionality
- Modify `index.html` for new UI elements
- Extend `lyrica.py` for additional API endpoints

## 📞 Support

If you encounter any issues:
1. Check the console logs in your browser (F12)
2. Look at the server logs in your terminal
3. Ensure all dependencies are installed
4. Try the sample songs first

---

**Happy singing! 🎵**
*Made with ❤️ in India 🇮🇳*
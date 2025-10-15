# Lyrica API - A Made in India Lyrics Finder

![Made in India](https://img.shields.io/badge/Made%20in-India-blue.svg) ![Python](https://img.shields.io/badge/Python-3.6%2B-brightgreen.svg) ![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**Lyrica** is a powerful, open-source lyrics finder API crafted in India 🇮🇳. It fetches song lyrics from multiple sources, starting with YouTube Music (thanks to sigma67 for the awesome `ytmusicapi`!) and falling back to Genius, Lyrics.ovh, ChartLyrics, LyricsFreek, and now **LrcLib** for even broader coverage and support for LRC timestamped lyrics. Built with Flask, Lyrica supports CORS for easy integration into web apps and provides detailed logging for debugging. Whether you're building a music app or just vibing to your favorite tracks, Lyrica has you covered! 
## WHAT'S NEW ?
- Now with gui to directly test api functionalities.
- To Use GUI GO TO :
  **`http://127.0.0.1:9999/app`**
- Added caching for fast response
- Added Simp music lyrics api for more lyrics support 
## Important 
Get your Genius API token here:  
https://genius.com/api-clients

It is important to fetch lyrics from lyricsgenius API.

1. Click on ‘New API Client’ in the left sidebar.  
2. In the box titled ‘App Website URL’ you can enter the url to any site hosted on GitHub pages or you can use https://es.python.org/ as a placeholder. It doesn’t really matter.  
3. Click save and you should see your API Client on a new page.  
4. If you click ‘Generate Access Token’ you’ll see your new Access Token and you’ll need to use that in this code to fetch lyrics from Genius.

## Features

- **Multi-Source Lyrics**: Prioritizes YouTube Music, with fallback to Genius, Lyrics.ovh, ChartLyrics, LyricsFreek, and LrcLib.
- **Timed Lyrics Support**: Get timestamped lyrics from YouTube Music and LrcLib (optional, if available).
- **LrcLib Integration**: Fetches LRC formatted, synchronized lyrics where available.
- **CORS Enabled**: Seamless integration with frontend applications.
- **Detailed Logging**: Track API attempts and errors for easy debugging.
- **Made in India**: Proudly developed with a focus on reliability and accessibility.

## How It Works

Lyrica API is designed to fetch song lyrics efficiently by querying multiple sources in a prioritized order:

1. **YouTube Music**: The API first attempts to retrieve lyrics using `ytmusicapi`, which may include timestamped lyrics for precise synchronization (e.g., for karaoke apps). Special thanks to sigma67 for making this possible!
2. **LrcLib**: If YouTube Music fails, Lyrica tries to fetch lyrics from [LrcLib](https://lrclib.net), supporting both plain and LRC timestamped lyrics. Special thanks  to tranxuanthang and Lrclib team for this amazing api.
3. **Fallback Sources**: If YouTube Music and LrcLib fail (e.g., no lyrics available or an error occurs), the API tries Genius, Lyrics.ovh, ChartLyrics, and LyricsFreek in sequence until lyrics are found or all sources are exhausted.
4. **Response Format**: Returns JSON with lyrics, source, artist, title, and timestamp. If LRC/timed lyrics are available, includes synchronized lines. If no lyrics are found, it provides detailed error messages and logs of attempted sources.
5. **CORS and Logging**: Supports cross-origin requests for web apps and logs each API attempt for debugging, making it developer-friendly.

The API runs on a Flask server, handling asynchronous requests for YouTube Music and LrcLib and synchronous requests for other sources, ensuring robust performance.

## Getting Started

### Prerequisites

- Python 3.6+
- Stable internet connection
- Genius API token (required for Genius source)

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/Wilooper/Lyrica.git
   cd Lyrica
   ```

2. Install dependencies:

   ```bash
   pip install flask[async] ytmusicapi lyricsgenius requests beautifulsoup4
   ```

   For LrcLib support (optional, but recommended):  
   LrcLib is accessed via HTTP API, so no extra package is required.

3. Set up YouTube Music authentication (if needed):

   ```bash
   ytmusicapi setup
   ```

   - Follow prompts to generate `headers_auth.json` and place it in the project directory.

4. Set the Genius API token:

   ```bash
   export GENIUS_TOKEN="your_genius_token"
   ```

   - Obtain a token from Genius API Clients and set it as an environment variable.

5. Run the API:

   ```bash
   python3 lyrica.py
   ```

   - The server runs on `http://127.0.0.1:9999`.

## How to Use for Best Results

To get the most out of Lyrica API, follow these tips:

- **Accurate Song and Artist Names**: Use precise names to improve search accuracy. For example, use "Arijit Singh" instead of "Arijit" and "Tum Hi Ho" instead of "Tum Hi".
- **URL Encoding**: Replace spaces with `%20` in URLs (e.g., `song=Tum%20Hi%20Ho`).
- **Timestamps for YouTube Music & LrcLib**: If you want timed lyrics (e.g., for karaoke or synced playback), add `&timestamps=true` to the request. Note: Timed lyrics are only available from YouTube Music and LrcLib, and not all songs support them.

  - **Example**: To get timed lyrics for "Blue Eyes" by Yo Yo Honey Singh:

    ```
    http://127.0.0.1:9999/lyrics/?artist=Yo%20Yo%20Honey%20Singh&song=Blue%20Eyes&timestamps=true
    ```

  - **Expected Result (if timed lyrics are available)**:

    ```json
    {
        "status": "success",
        "data": {
            "source": "youtube_music",
            "artist": "Yo Yo Honey Singh",
            "title": "Blue Eyes",
            "lyrics": "Blue eyes hypnotize teri kardi ai mennu\nI swear chhoti dress mein bomb lagdi mennu\n...",
            "timed_lyrics": [
                {
                    "text": "Blue eyes hypnotize teri kardi ai mennu",
                    "start_time": 9200,
                    "end_time": 10630,
                    "id": 1
                },
                {
                    "text": "I swear chhoti dress mein bomb lagdi mennu",
                    "start_time": 10680,
                    "end_time": 12540,
                    "id": 2
                }
            ],
            "hasTimestamps": true,
            "timestamp": "2025-06-26 14:13:00"
        },
        "attempts": []
    }
    ```

  - **Expected Result (if LrcLib timed lyrics are available)**:

    ```json
    {
        "status": "success",
        "data": {
            "source": "lrclib",
            "artist": "Yo Yo Honey Singh",
            "title": "Blue Eyes",
            "lyrics": "Blue eyes hypnotize teri kardi ai mennu\n...",
            "timed_lyrics": [
                {
                    "text": "Blue eyes hypnotize teri kardi ai mennu",
                    "start_time": 0,
                    "end_time": 10630,
                    "id": 1
                }
            ],
            "hasTimestamps": true,
            "timestamp": "2025-06-26 14:13:00"
        },
        "attempts": []
    }
    ```

  - **Expected Result (if timed lyrics are unavailable)**:

    ```json
    {
        "status": "success",
        "data": {
            "source": "youtube_music",
            "artist": "Yo Yo Honey Singh",
            "title": "Blue Eyes",
            "lyrics": "Blue eyes hypnotize teri kardi ai mennu\nI swear chhoti dress mein bomb lagdi mennu\n...",
            "timestamp": "2025-06-26 14:13:00"
        },
        "attempts": []
    }
    ```

- **Try Popular Songs**: Popular tracks (e.g., Bollywood hits like "Tum Hi Ho" by Arijit Singh) are more likely to have lyrics available across multiple sources.
- **Check Logs**: If lyrics aren’t found, check the server logs (`lyrica.py` output) for specific errors (e.g., "No lyrics available for this song").
- **Test with Browser or Tools**: Use a browser, `curl`, or tools like Postman to test requests and view JSON responses.

## API Endpoints

### 1. Home

- **URL**: `http://127.0.0.1:9999/`
- **TO USE GUI**: `http://127.0.0.1:9999/app`
  

- **Method**: GET

- **Description**: Returns API metadata, including version, status, and supported sources.

- **Example Response**:

  ```json
  {
      "api": "Lyrica API",
      "version": "1.2",
      "status": "active",
      "endpoints": {
          "lyrics": "/lyrics/?artist=ARTIST&song=SONG[&timestamps=true]"
      },
      "supported_sources": ["YouTube Music", "LrcLib", "Genius", "Lyrics.ovh", "ChartLyrics", "LyricsFreek"],
      "timestamp": "2025-06-26 14:13:00"
  }
  ```

### 2. Lyrics

- **URL**: `http://127.0.0.1:9999/lyrics/?artist=ARTIST&song=SONG[&timestamps=true]`

- **Method**: GET

- **Description**: Fetches lyrics for a given song and artist, trying YouTube Music first, then LrcLib, then falling back to other sources.

- **Query Parameters**:

  - `artist` (required, string): Artist name (e.g., "Arijit Singh").
  - `song` (required, string): Song title (e.g., "Tum Hi Ho"). Use `%20` for spaces (e.g., `song=Tum%20Hi%20Ho`).
  - `timestamps` (optional, boolean): Set to `true` for timed lyrics from YouTube Music or LrcLib. Defaults to `false`.

- **Example Requests**:

  ```
  http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho
  http://127.0.0.1:9999/lyrics/?artist=Yo%20Yo%20Honey%20Singh&song=Blue%20Eyes&timestamps=true
  ```

- **Success Response (YouTube Music)**:

  ```json
  {
      "status": "success",
      "data": {
          "source": "youtube_music",
          "artist": "Arijit Singh",
          "title": "Tum Hi Ho",
          "lyrics": "Hum tere bin ab reh nahi sakte\nTere bina kya wajood mera\n...",
          "timestamp": "2025-06-26 14:13:00"
      },
      "attempts": []
  }
  ```

- **Success Response (LrcLib with Timestamps)**:

  ```json
  {
      "status": "success",
      "data": {
          "source": "lrclib",
          "artist": "Arijit Singh",
          "title": "Tum Hi Ho",
          "lyrics": "Hum tere bin ab reh nahi sakte\nTere bina kya wajood mera\n...",
          "timed_lyrics": [
              {
                  "text": "Hum tere bin ab reh nahi sakte",
                  "start_time": 0,
                  "end_time": 10000,
                  "id": 1
              }
          ],
          "hasTimestamps": true,
          "timestamp": "2025-06-26 14:13:00"
      },
      "attempts": []
  }
  ```

- **Success Response (Fallback, e.g., Genius)**:

  ```json
  {
      "status": "success",
      "data": {
          "source": "genius",
          "artist": "Arijit Singh",
          "title": "Tum Hi Ho",
          "lyrics": "Hum tere bin ab reh nahi sakte\nTere bina kya wajood mera\n...",
          "timestamp": "2025-06-26 14:13:00"
      },
      "attempts": [
          {
              "api": "YouTube Music",
              "status": "no_results",
              "message": "No lyrics available for this song"
          },
          {
              "api": "LrcLib",
              "status": "no_results"
          }
      ]
  }
  ```

- **Error Response (Missing Parameters)**:

  ```json
  {
      "status": "error",
      "error": {
          "message": "Artist and song name are required",
          "timestamp": "2025-06-26 14:13:00"
      }
  }
  ```

  HTTP Status Code: 400

- **Error Response (No Lyrics Found)**:

  ```json
  {
      "status": "error",
      "error": {
          "message": "No lyrics found for 'Tum Hi Ho' by 'Arijit Singh'",
          "attempts": [
              {
                  "api": "YouTube Music",
                  "status": "no_results",
                  "message": "No lyrics available for this song"
              },
              {
                  "api": "LrcLib",
                  "status": "no_results"
              },
              {
                  "api": "Genius",
                  "status": "no_results"
              },
              {
                  "api": "Lyrics.ovh",
                  "status": "no_results"
              },
              {
                  "api": "ChartLyrics",
                  "status": "no_results"
              },
              {
                  "api": "LyricsFreek",
                  "status": "no_results"
              }
          ]
      },
      "timestamp": "2025-06-26 14:13:00"
  }
  ```

## Usage Example

Using `curl`:

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Yo%20Yo%20Honey%20Singh&song=Blue%20Eyes"
```

In a browser:

```
http://127.0.0.1:9999/lyrics/?artist=Yo%20Yo%20Honey%20Singh&song=Blue%20Eyes&timestamps=true
```

With JavaScript (e.g., in a frontend):

```javascript
fetch('http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho')
    .then(response => response.json())
    .then(data => console.log(data));
```
## Special query 
There are some special queries which you can use after & timestamp query.
To enable special query use ```&pass=true```after timestamp querry.
Now you can use ```&sequence=your sequence to use api```
this can be use to make your own sequence of using api tools to featch lyrics.If you want Lyrica to skip a api then use ```&pass=true&sequence=1,3,4,5,6```
in this  example it will not search for no 2 api and directly skip to third one.
You can use them to make your search faster.
   "1": "Genius",
    "2": "LRCLIB",
    "3": "YouTube Music",
    "4": "Lyrics.ovh",
    "5": "ChartLyrics",
    "6": "LyricsFreek"
 This is the series of api you need to correct number in sequence parameter  to get your desire result use list above mentioned for this purpose 
## Note
The given JSON data is only for reference and you may not get the same response for the same query because these are only for example purposes.

## Supported Sources

1. **YouTube Music**: Primary source, supports plain and timed lyrics (thanks to sigma67).
2. **LrcLib**: Synchronized LRC/timed and plain lyrics from [LrcLib](https://lrclib.net) API.
3. **Genius**: Rich lyrics with artist verification.
4. **Lyrics.ovh**: Simple and fast lyrics API.
5. **ChartLyrics**: XML-based lyrics source.
6. **LyricsFreek**: Web-scraped lyrics for broader coverage.

## Troubleshooting

- **Async Errors**: Ensure `flask[async]` is installed:

  ```bash
  pip install flask[async]
  ```

- **YouTube Music Authentication**: Run `ytmusicapi setup` if you see authentication errors. Place `headers_auth.json` in the project directory.

- **Genius Token Issues**: Get a valid token from Genius API Clients and set it via `export GENIUS_TOKEN="your_token"`.

- **No Lyrics Found**: Some songs may not have lyrics in any source. Try popular tracks or check logs (`lyrica.py` output).

- **Port Conflicts**: If port 9999 is busy, edit the script to use another port (e.g., `app.run(port=8080)`).

- **Network Issues**: Ensure a stable internet connection, especially on Termux or mobile environments.

## Deployment Notes

- The Flask development server (`app.run()`) is not suitable for production. Use a WSGI server like Gunicorn:

  ```bash
  pip install gunicorn
  gunicorn -w 4 -b 0.0.0.0:9999 lyrica:app
  ```

- Pair with a reverse proxy (e.g., Nginx) for production use.

- Set environment variables securely in production (e.g., avoid hardcoding `GENIUS_TOKEN`).

## Contributing

Contributions are welcome! 🎉

- Fork the repo, make changes, and submit a pull request.
- Report issues or suggest features via GitHub Issues.
- Follow the code style in `lyrica.py`.

## Special Thanks

- **sigma67**: For creating the `ytmusicapi`, which powers Lyrica’s YouTube Music integration.
- **tranxuanthang** and the **LrcLib team**: For the amazing [LrcLib API](https://lrclib.net), enabling synchronized LRC/timed lyrics support in Lyrica.
- **maxrave-dev**:For amazing Simp music lyrics library 

## License

MIT License. See LICENSE for details.

## Contact

Proudly made in India 🇮🇳. For support, open an issue on GitHub or reach out to the maintainer.

---

*Sing along with Lyrica, your go-to lyrics finder!*

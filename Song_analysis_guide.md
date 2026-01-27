# Song Meaning Analyzer API User Guide

## Introduction

Welcome to the Song Meaning Analyzer API! This service helps you dive deep into song lyrics. You can get summaries of song meanings, break down lyrics line by line, identify themes, or spot poetic devices like metaphors and rhymes. It pulls lyrics from Lyrica and uses AI to analyze them.
**Note before proceeding**
- This version may have a lot of bugs as it is in early stages so you may have to face trouble.
- If you want to help me plese let me know on `thinkelyorg@gmail.com`
i will reply asap
**Base URL:** `https://terx.onrender.com`

**Note for Beginners:** If you're new to APIs, think of this as a web tool where you send requests (like searching on Google) and get back structured data about songs. You can test it in your browser or use simple tools like Postman.

**Note for Developers:** This API is built with Flask and integrates with external services like OpenRouter for AI and Lyrica for music data. It's open for integration into apps, bots, or websites. 

This is an **early version**, so you might run into bugs, slow responses, or missing features. If something doesn't work, try again later or report it. We're improving it based on feedback!

## Rate Limits

To keep things fair and avoid overloading free services (like AI models), we have limits:

- **General Requests:** Up to 10 requests per minute from your IP address. If you go over, you'll get a "429 Too Many Requests" error—wait a minute and try again.
- **AI-Heavy Requests:** Things like full song analysis are capped at 5 per hour because they use external AI that has its own limits.
- **Tips to Avoid Limits:**
  - Don't send requests too quickly (wait 5-10 seconds between them).
  - Check the `/health` endpoint first to see if the API is up.
  - For high-volume use, contact us for possible upgrades.

If you're a beginner, rate limits just mean "don't spam the API." For developers, monitor your app's request rate and handle 429 errors gracefully (e.g., with retries).

## Getting Started

### For Beginners
1. **Test in Browser:** Just type the URL in your web browser. For example, go to `https://terx.onrender.com/health` to check if it's working.
2. **Tools to Use:** 
   - Browser for simple GET requests.
   - [Postman](https://www.postman.com/) or [Insomnia](https://insomnia.rest/) for trying endpoints.
3. **URL Encoding:** If names have spaces (e.g., "Taylor Swift"), replace spaces with `%20` (e.g., `Taylor%20Swift`).

### For Developers
- **HTTP Methods:** Mostly GET, one POST for clearing cache.
- **Authentication:** None needed—it's open!
- **Response Format:** Always JSON. Parse it in your code.
- **Example in Curl (Command Line):**
  ```bash
  curl https://terx.onrender.com/Arijit%20Singh/Tum%20Hi%20Ho/full
  ```
- **Example in Python (using requests):**
  ```python
  import requests

  response = requests.get("https://terx.onrender.com/Arijit%20Singh/Tum%20Hi%20Ho/full")
  if response.status_code == 200:
      data = response.json()
      print(data)
  else:
      print(f"Error: {response.status_code}")
  ```
- **Libraries:** Use `requests` in Python, `fetch` in JavaScript, or similar for easy integration.

## Endpoints

All endpoints return JSON. Examples include curl commands for easy testing.

### 1. Root (API Overview)
- **Method:** GET
- **Path:** `/`
- **Description:** Gives a quick summary of the API, endpoints, and examples. Great starting point.
- **Example:**
  ```bash
  curl https://terx.onrender.com/
  ```
- **Response Snippet:**
  ```json
  {
    "api": "Song Meaning Analyzer API",
    "version": "2.0",
    // more info...
  }
  ```

### 2. Health Check
- **Method:** GET
- **Path:** `/health`
- **Description:** Checks if the API is running and lists endpoints/methods. Use this to monitor status.
- **Example:**
  ```bash
  curl https://terx.onrender.com/health
  ```
- **Response Snippet:**
  ```json
  {
    "status": "ok",
    "service": "Song Meaning Analyzer API",
    // endpoints...
  }
  ```

### 3. Main Analysis
- **Method:** GET
- **Path:** `/{artist}/{song}/{analysis_method}`
- **Description:** The core feature! Analyzes a song. Methods:
  - `full`: Overall meaning, themes, context.
  - `line-by-line`: Breaks down each lyric line.
  - `themes`: Lists main ideas and emotions.
  - `poetic-devices`: Spots rhymes, metaphors, etc.
- **Example:**
  ```bash
  curl https://terx.onrender.com/The%20Weeknd/Blinding%20Lights/line-by-line
  ```
- **Response Snippet (simplified):**
  ```json
  {
    "status": "success",
    "analysis": {
      // detailed breakdown...
    }
  }
  ```

### 4. Song Search
- **Method:** GET
- **Path:** `/search/{artist}/{song}`
- **Description:** Gets lyrics and basic info (no analysis). Good for quick checks.
- **Example:**
  ```bash
  curl https://terx.onrender.com/search/Taylor%20Swift/Anti-Hero
  ```
- **Response Snippet:**
  ```json
  {
    "status": "success",
    "data": {
      "lyrics": "Song lyrics here...",
      // metadata...
    }
  }
  ```

### 5. JioSaavn Search
- **Method:** GET
- **Path:** `/jiosaavn/search/{query}`
- **Description:** Searches songs on JioSaavn (music platform). Returns matches with details.
- **Example:**
  ```bash
  curl https://terx.onrender.com/jiosaavn/search/Arctic%20Monkeys
  ```
- **Response Snippet:**
  ```json
  {
    "status": "success",
    "results": [
      // song list...
    ]
  }
  ```

### 6. Cache Stats
- **Method:** GET
- **Path:** `/cache/stats`
- **Description:** Shows how many analyses are cached (speeds up repeats).
- **Example:**
  ```bash
  curl https://terx.onrender.com/cache/stats
  ```
- **Response Snippet:**
  ```json
  {
    "cache_entries": 3,
    "cached_songs": ["..."]
  }
  ```

### 7. Clear Cache
- **Method:** POST
- **Path:** `/cache/clear`
- **Description:** Resets the cache. Use if data seems outdated.
- **Example:**
  ```bash
  curl -X POST https://terx.onrender.com/cache/clear
  ```
- **Response Snippet:**
  ```json
  {
    "status": "success",
    "cleared": 3
  }
  ```

## Error Handling

- **Common Errors:**
  - **400:** Bad input (e.g., wrong method).
  - **404:** Song not found.
  - **429:** Too many requests—wait and retry.
  - **500:** Server bug—report it!
- **In Code:** Check `status` in JSON: "success" or "error" with a message.
- **Tip:** For devs, add try-catch in your code to handle failures.

## Tips and Best Practices

- **Beginners:** Start with browser tests. If lyrics aren't found, try different spellings (e.g., title case like "Blinding Lights").
- **Developers:** Cache results in your app too. Handle URL encoding automatically (e.g., Python's `urllib.parse.quote`).
- **Common Issues:** Slow AI responses—be patient. Obscure songs might not have lyrics.
- **Feedback:** If you spot bugs, let us know (e.g., via email or issues).

Thanks for using the API! Whether you're a newbie exploring songs or a dev building cool apps, we hope this helps. Happy analyzing! 🎵

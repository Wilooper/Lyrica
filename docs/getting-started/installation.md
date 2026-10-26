# Installation Guide

This guide walks you through setting up Lyrica on Linux, macOS, or Windows.

---

## System Requirements

- **Python**: Version `3.11` or higher (`3.11`, `3.12`, or `3.13`)
- **Git**: For source version control
- **Memory**: Minimum 256 MB RAM (512 MB+ recommended)
- **Optional**: Redis 6+ (enables L2 distributed cache across multiple workers)
- **Optional**: `ffmpeg` (only if using YouTube caption fallback streams)

---

## Local Environment Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Wilooper/Lyrica.git
cd Lyrica
```

### 2. Create and Activate Virtual Environment

=== "Linux & macOS"
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

=== "Windows (PowerShell)"
    ```powershell
    python -m venv venv
    .\venv\Scripts\Activate.ps1
    ```

=== "Windows (CMD)"
    ```cmd
    python -m venv venv
    .\venv\Scripts\activate.bat
    ```

### 3. Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the example environment template:

```bash
cp .env.example .env
```

Open `.env` in your text editor. Lyrica works out of the box with default public providers, but you can configure optional tokens:

```ini
# Optional: Admin authentication key for cache invalidation & proxy admin
ADMIN_KEY=your_secure_admin_key_here

# Optional: Genius client access token (optional — public search works as fallback)
GENIUS_TOKEN=

# Optional: Groq API key for translation and romanization
GROQ_API_KEY=

# Optional: Apple Music Developer token for syllable & word sync
APPLE_MUSIC_DEVELOPER_TOKEN=

# Optional: Redis connection for distributed L2 cache
REDIS_URL=redis://localhost:6379/0
```

### 5. Start the Development Server

```bash
python run.py
```

Output:

```
 * Serving Flask app 'src.app'
 * Debug mode: off
 * Running on http://127.0.0.1:9999
```

---

## Docker Installation

For containerized deployment, see the dedicated [Docker Deployment Guide](../deployment/docker.md).

```bash
# Production Docker Compose (Lyrica API + Redis)
docker compose up -d
```
The container exposes port `7860`.

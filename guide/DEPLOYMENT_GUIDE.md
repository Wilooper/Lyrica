# 🚀 Lyrica — Production Deployment Guide

This guide provides comprehensive, step-by-step instructions for deploying **Lyrica** across various cloud hosting platforms, container environments, and self-hosted Linux VPS setups.

---

## 📌 Table of Contents

1. [Environment Setup & Secrets](#environment-setup--secrets)
2. [Option 1: Docker & Docker Compose (Recommended)](#option-1-docker--docker-compose-recommended)
3. [Option 2: Self-Hosted Linux VPS (Gunicorn + Nginx + SSL)](#option-2-self-hosted-linux-vps-gunicorn--nginx--ssl)
4. [Option 3: Render.com](#option-3-rendercom)
5. [Option 4: Hugging Face Spaces (Docker / Python)](#option-4-hugging-face-spaces-docker--python)
6. [Option 5: Railway.app](#option-5-railwayapp)
7. [Option 6: Vercel (Serverless / WSGI)](#option-6-vercel-serverless--wsgi)
8. [Option 7: Fly.io](#option-7-flyio)
9. [Option 8: Koyeb / Heroku](#option-8-koyeb--heroku)
10. [Production Tuning & Best Practices](#production-tuning--best-practices)

---

## 🔑 Environment Setup & Secrets

Before deploying to any platform, configure your environment variables:

```env
# Mandatory for Admin Endpoints
ADMIN_KEY=your_super_secret_admin_key_123

# Optional Source Tokens
GENIUS_TOKEN=your_genius_client_token
MUSIXMATCH_TOKEN=your_musixmatch_client_token

# Groq LLM Translation Keys (Comma-separated for round-robin)
# Note: Groq may deprecate or remove support for specific models at any time.
# Override GROQ_MODEL with any available Groq model if the default is removed.
GROQ_API_KEY=gsk_key1,gsk_key2
GROQ_MODEL=openai/gpt-oss-120b


# Proxy Pool (Protects against data center IP blocks on YouTube/Genius)
PROXY_URL=http://user:pass@proxy1.com:8080,socks5://proxy2.com:1080
YT_PROXY_URL=http://user:pass@ytproxy.com:8080

# YouTube Cookies / Headers (For hosted cloud servers)
YT_COOKIES_PATH=/app/security/cookies.txt
YT_HEADERS_PATH=/app/security/headers_auth.json

# Cache & Rate Limiter Configuration
RATE_LIMIT_STORAGE_URI=memory://
CACHE_TTL=86400
LOG_LEVEL=INFO
```

---

## 🐳 Option 1: Docker & Docker Compose (Recommended)

### Using Docker CLI

1. **Build the Docker Image**:
   ```bash
   docker build -t lyrica:1.4.0 .
   ```

2. **Run Container**:
   ```bash
   docker run -d \
     --name lyrica_api \
     -p 9999:9999 \
     --env-file .env \
     -v $(pwd)/cache_data:/app/cache_data \
     lyrica:1.4.0
   ```

### Using Docker Compose

Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  lyrica:
    build: .
    container_name: lyrica_api
    restart: always
    ports:
      - "9999:9999"
    env_file:
      - .env
    volumes:
      - ./cache_data:/app/cache_data
      - ./security:/app/security
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9999/"]
      interval: 30s
      timeout: 5s
      retries: 3

  redis:
    image: redis:7-alpine
    container_name: lyrica_redis
    restart: always
    ports:
      - "6379:6379"
```

Run compose:
```bash
docker-compose up -d
```

---

## 🖥️ Option 2: Self-Hosted Linux VPS (Gunicorn + Nginx + SSL)

Tested on **Ubuntu 22.04 / 24.04 LTS**.

### 1. System Setup & Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv nginx certbot python3-certbot-nginx git -y
```

### 2. Clone Repository & Setup Virtual Environment

```bash
cd /var/www
sudo git clone https://github.com/Wilooper/Lyrica.git
cd Lyrica

sudo python3 -m venv venv
sudo ./venv/bin/pip install -r requirements.txt

sudo cp .env.example .env
sudo nano .env   # Set ADMIN_KEY, GROQ_API_KEY, PROXY_URL
```

### 3. Create Systemd Service (`/etc/systemd/system/lyrica.service`)

Create service file:

```ini
[Unit]
Description=Lyrica REST API Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/Lyrica
ExecStart=/var/www/Lyrica/venv/bin/gunicorn -w 4 -b 127.0.0.1:9999 --timeout 120 run:app
Restart=always
RestartSec=5
EnvironmentFile=/var/www/Lyrica/.env

[Install]
WantedBy=multi-user.target
```

Enable and start service:

```bash
sudo chown -R www-data:www-data /var/www/Lyrica
sudo systemctl daemon-reload
sudo systemctl enable lyrica
sudo systemctl start lyrica
sudo systemctl status lyrica
```

### 4. Configure Nginx Reverse Proxy (`/etc/nginx/sites-available/lyrica`)

```nginx
server {
    server_name lyrica.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:9999;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 120s;
    }
}
```

Enable site & reload Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/lyrica /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5. Obtain Free SSL Certificate (Certbot)

```bash
sudo certbot --nginx -d lyrica.yourdomain.com
```

---

## ☁️ Option 3: Render.com

1. Push your repository to GitHub.
2. Log in to [Render Dashboard](https://dashboard.render.com/) and click **New +** → **Web Service**.
3. Connect your `Lyrica` GitHub repository.
4. Set settings:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn -w 4 -b 0.0.0.0:9999 run:app`
5. Under **Environment Variables**, add:
   - `ADMIN_KEY`
   - `GROQ_API_KEY`
   - `PROXY_URL` (Recommended for data center IPs)
6. Click **Create Web Service**.

---

## 🎨 Option 4: Hugging Face Spaces (Docker / Python)

1. Create a new Space on [Hugging Face](https://huggingface.co/new-space).
2. Choose **SDK**: `Docker` or `Gradio/Blank`.
3. If using Docker, upload your `Dockerfile` and repository files.
4. Under Space Settings → **Variables and Secrets**, add your `.env` variables (`ADMIN_KEY`, `GROQ_API_KEY`, `PROXY_URL`).
5. Ensure your Dockerfile exposes port `7860` (Hugging Face default) or set:
   ```dockerfile
   EXPOSE 7860
   CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:7860", "run:app"]
   ```

---

## 🚂 Option 5: Railway.app

1. Install Railway CLI or connect via GitHub on [Railway.app](https://railway.app/).
2. Click **New Project** → **Deploy from GitHub repo**.
3. Select `Lyrica`.
4. Add Environment Variables under **Variables**.
5. Railway automatically detects `requirements.txt` and uses `Procfile` or start command:
   `gunicorn -w 4 -b 0.0.0.0:$PORT run:app`

---

## ⚡ Option 6: Vercel (Serverless / WSGI)

Create a `vercel.json` file in your repository root:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "run.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "run.py"
    }
  ]
}
```

Add your environment variables in Vercel Project Settings and run `vercel --prod`.

---

## ✈️ Option 7: Fly.io

1. Install Fly CLI (`flyctl`).
2. Run `fly launch` in project directory.
3. Configure `fly.toml`:
   ```toml
   app = "lyrica-api"
   primary_region = "iad"

   [build]

   [http_service]
     internal_port = 9999
     force_https = true
     auto_stop_machines = false
     auto_start_machines = true
     min_machines_running = 1
   ```
4. Set secrets:
   ```bash
   fly secrets set ADMIN_KEY="your_key" GROQ_API_KEY="gsk_key" PROXY_URL="http://..."
   ```
5. Deploy with `fly deploy`.

---

## 🚀 Option 8: Koyeb / Heroku

### Procfile (for Heroku & Koyeb)

Create a `Procfile` in project root:

```
web: gunicorn -w 4 -b 0.0.0.0:$PORT run:app
```

Deploy via git push:
```bash
heroku create lyrica-api
git push heroku main
```

---

## ⚙️ Production Tuning & Best Practices

1. **Proxy Pool**: Hosted cloud environments (AWS, GCP, Render, HF) are frequently blocked by YouTube and Genius. Always set `PROXY_URL` in `.env` to route requests through proxy servers.
2. **Gunicorn Workers**: Use `(2 * CPU cores) + 1` workers. For a 2-core VPS, use `-w 5`.
3. **Redis Rate Limiting**: In high-concurrency environments, switch `RATE_LIMIT_STORAGE_URI` from `memory://` to Redis (`redis://localhost:6379/0`) to share rate limit counters across workers.
4. **Cache Persistence**: Ensure `cache_data/` directory is mounted on a persistent volume if using ephemeral containers.

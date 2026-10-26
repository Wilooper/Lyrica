# Cloud Platforms & VPS Deployment

This guide covers deploying Lyrica to major cloud hosting providers and self-hosted Linux VPS environments.

---

## 1. Hugging Face Spaces (Docker / Python)

Hugging Face Spaces natively supports Docker containers and expects services on port `7860`.

1. Create a new Space on [Hugging Face](https://huggingface.co/spaces).
2. Choose **Docker** as the SDK (Blank template).
3. Push the Lyrica repository to your Hugging Face Space Git remote:
   ```bash
   git remote add space https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE_NAME
   git push space main
   ```
4. In your Space settings, add environment secrets under **Settings > Variables and secrets**:
   - `ADMIN_KEY`
   - `GROQ_API_KEY` (if using translation)
   - `GENIUS_TOKEN` (optional)
   - `APPLE_MUSIC_DEVELOPER_TOKEN` (optional)

---

## 2. Render.com

Lyrica runs seamlessly on Render as a Web Service:

1. Click **New > Web Service** in the Render Dashboard.
2. Connect your Git repository.
3. Configure settings:
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn -c gunicorn_production.py run:app`
4. Add environment variables in the Render dashboard:
   - `PYTHON_VERSION`: `3.11.9`
   - `LYRICA_ENV`: `production`
   - `ADMIN_KEY`: `<your_secret>`

---

## 3. Self-Hosted Linux VPS (Ubuntu/Debian + Nginx + SSL)

For self-hosting on a DigitalOcean droplet, Hetzner VPS, AWS EC2, or Linode:

### Step 1: System Dependencies & Repository Setup

```bash
sudo apt update && sudo apt install -y python3-pip python3-venv git nginx certbot python3-certbot-nginx
git clone https://github.com/Wilooper/Lyrica.git /opt/lyrica
cd /opt/lyrica
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Step 2: Create Systemd Service (`/etc/systemd/system/lyrica.service`)

```ini
[Unit]
Description=Lyrica Lyrics API
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/lyrica
Environment="PATH=/opt/lyrica/venv/bin"
EnvironmentFile=/opt/lyrica/.env
ExecStart=/opt/lyrica/venv/bin/gunicorn -c gunicorn_production.py run:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now lyrica
```

### Step 3: Configure Nginx Reverse Proxy (`/etc/nginx/sites-available/lyrica`)

```nginx
server {
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:7860;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/lyrica /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d api.yourdomain.com
```

---

## 4. Railway.app

1. Click **New Project > Deploy from GitHub repo**.
2. Railway detects `Dockerfile` automatically.
3. Add a **Redis** service from the Railway Marketplace and link `REDIS_URL`.
4. Configure variables in the Railway dashboard (`PORT=7860`, `ADMIN_KEY=...`).

---

## 5. Vercel (Serverless WSGI)

Lyrica includes native Vercel configuration (`vercel.json` and `pyproject.toml`):

```json
{
  "version": 2,
  "rewrites": [
    { "source": "/(.*)", "destination": "run.py" }
  ]
}
```

Deploy using the Vercel CLI:

```bash
vercel --prod
```

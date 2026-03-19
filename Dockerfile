FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PATH="/root/.local/bin:$PATH" PORT=7860
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc git ffmpeg libxml2-dev libxslt1-dev libffi-dev libssl-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY . /app
EXPOSE 7860
CMD ["gunicorn", "-c", "gunicorn.config.py", "run:app"]
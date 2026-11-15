FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LYRICA_MCP_TRANSPORT=streamable-http \
    LYRICA_MCP_HOST=0.0.0.0 \
    LYRICA_MCP_PORT=8000 \
    LYRICA_MCP_PATH=/mcp \
    LYRICA_API_URL=http://host.docker.internal:9999

WORKDIR /app

COPY pyproject.toml README.md ./
COPY lyrica_mcp ./lyrica_mcp

RUN pip install .

RUN useradd --create-home --uid 10001 mcp
USER mcp

EXPOSE 8000

ENTRYPOINT ["lyrica-mcp"]

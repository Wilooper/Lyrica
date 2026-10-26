# Contributing to Lyrica

Thank you for your interest in contributing to **Lyrica**! We welcome bug fixes, documentation improvements, new provider integrations, and performance optimizations.

---

## Code of Conduct

All contributors and participants are expected to adhere to our [Code of Conduct](https://github.com/Wilooper/Lyrica/blob/main/CODE_OF_CONDUCT.md). Please treat others with respect and constructive collaboration.

---

## Development Workflow

1. **Fork the Repository**: Create a personal fork on GitHub.
2. **Clone and Branch**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/Lyrica.git
   cd Lyrica
   git checkout -b feature/your-feature-name
   ```
3. **Set Up Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
4. **Implement and Test**: Write your code and ensure all tests pass:
   ```bash
   python Test/run_all_tests.py
   ```
5. **Submit a Pull Request**: Push your branch to GitHub and open a Pull Request against `main`.

---

## Core Coding Conventions

Please follow these established repository standards:

1. **Async Non-Blocking Pattern**:
   - All network calls must use `httpx.AsyncClient` or the shared client from `get_http_client()`.
   - Never use `requests` or blocking socket I/O in provider pathways.
   - Never introduce heavy HTML parsing libraries (`bs4`) into fast runtime paths. Use linear tag-depth tracking or regex.

2. **Standardized Response Shapes**:
   - Always return dictionaries constructed with `build_result()` from `src/sources/base_fetcher.py`.
   - Maintain the standard `{"status": "success", "data": {...}}` response envelope.

3. **Multi-Tier Caching**:
   - Ensure new query parameters are incorporated into `make_cache_key()` in `src/cache.py` to prevent cache collision across differing request configurations.

---

## Adding a New Lyrics Provider

To integrate a new lyrics source:

1. **Create the Fetcher**: Add `src/sources/yourprovider_fetcher.py` inheriting from `BaseFetcher`:
   ```python
   from .base_fetcher import BaseFetcher, build_result, get_http_client

   class YourProviderFetcher(BaseFetcher):
       source_name = "yourprovider"

       async def fetch(self, artist: str, song: str, timestamps: bool = False):
           client = get_http_client()
           # Implement fetch logic
           return build_result(
               source=self.source_name,
               artist=artist,
               title=song,
               lyrics=lyrics_text,
               hasTimestamps=timestamps,
           )
   ```
2. **Register the Source**:
   - Import your fetcher in `src/fetch_controller.py`.
   - Assign a new integer source ID in the provider registry.
   - Update fallback phase lists.
3. **Add Tests**: Write unit and integration assertions in `Test/`.
4. **Update Documentation**: Add your provider to `docs/providers/overview.md`.

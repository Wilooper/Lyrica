"""
Test/test_real_genius.py

Live integration tests for the Genius lyrics source fetcher against real-world songs.
Validates:
1. Public & official search integration
2. Verse and section completeness (no missing verses)
3. Exclusion of Genius UI artifacts (contributor tags, translation dropdowns, ads)
4. Clean text extraction without HTML entities or obscure Unicode spacing
"""

import os
import sys
import asyncio
import time

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.sources.genius_fetcher import GeniusFetcher, _parse_lyrics_page, _extract_container_contents

# Live integration tests are opt-in: upstream outages and rate limits must not
# make the default test suite (or CI) red.
_LIVE = pytest.mark.skipif(
    os.getenv("LYRICA_RUN_INTEGRATION", "0") != "1",
    reason="live Genius integration test — set LYRICA_RUN_INTEGRATION=1 to enable",
)


@_LIVE
async def test_live_the_weeknd():
    print("\n[TEST 1] Fetching live song: 'The Weeknd - Blinding Lights'...")
    start_time = time.perf_counter()
    fetcher = GeniusFetcher()
    result = await fetcher.fetch(artist="The Weeknd", song="Blinding Lights")
    elapsed = time.perf_counter() - start_time

    assert result is not None, "Failed to fetch 'The Weeknd - Blinding Lights' from Genius"
    assert result.get("source") == "genius"
    assert "The Weeknd" in result.get("artist", "")
    assert "Blinding Lights" in result.get("title", "")

    lyrics = result.get("lyrics", "")
    lines = lyrics.splitlines()

    print(f"  -> Fetched in {elapsed:.2f}s | {len(lines)} lines | {len(lyrics.split())} words")

    # 1. Completeness verification — key sections must be present
    assert "[Verse 1]" in lyrics or "tryna call" in lyrics.lower(), "Missing Verse 1"
    assert "[Chorus]" in lyrics or "blinded by the lights" in lyrics.lower(), "Missing Chorus"
    assert "[Outro]" in lyrics or "feel your touch" in lyrics.lower(), "Missing Outro"

    # 2. Cleanup verification — UI artifacts must NOT be present
    assert "Contributors" not in lyrics, "Leaked contributor badge text"
    assert "Translations" not in lyrics, "Leaked translation header"
    assert "Embed" not in lyrics, "Leaked Genius embed counter"
    assert "<div" not in lyrics and "</div>" not in lyrics, "Leaked HTML div tags"
    assert "&amp;" not in lyrics and "&quot;" not in lyrics, "Unescaped HTML entities"

    print("  [PASS] 'The Weeknd - Blinding Lights' fetched with complete verses & clean formatting.")


@_LIVE
async def test_live_queen():
    print("\n[TEST 2] Fetching live song: 'Queen - Bohemian Rhapsody'...")
    start_time = time.perf_counter()
    fetcher = GeniusFetcher()
    result = await fetcher.fetch(artist="Queen", song="Bohemian Rhapsody")
    elapsed = time.perf_counter() - start_time

    assert result is not None, "Failed to fetch 'Queen - Bohemian Rhapsody' from Genius"
    assert result.get("source") == "genius"

    lyrics = result.get("lyrics", "")
    print(f"  -> Fetched in {elapsed:.2f}s | {len(lyrics.splitlines())} lines | {len(lyrics.split())} words")

    # Key verses
    assert "Is this the real life?" in lyrics
    assert "Mama, just killed a man" in lyrics
    assert "Scaramouche" in lyrics or "Galileo" in lyrics
    assert "Nothing really matters" in lyrics

    # Cleanliness
    assert "Contributors" not in lyrics
    assert "Embed" not in lyrics

    print("  [PASS] 'Queen - Bohemian Rhapsody' fetched with all operatic and rock sections intact.")


def test_parser_adversarial_nested_html():
    print("\n[TEST 3] Testing parser resilience against adversarial nested DOM structures...")
    # Multi-container HTML with nested divs, ads in-between, and contributor tags
    sample_html = """
    <html>
    <body>
      <div data-lyrics-container="true">
        <div data-exclude-from-selection="true">
          <button><span>42 Contributors</span></button>
          <div><span>Translations: French, Spanish</span></div>
        </div>
        [Intro]<br>
        Deep nested verse line 1<br>
        <div>
          <span><div>Deep nested verse line 2</div></span>
        </div>
      </div>
      <div class="SponsoredAdContainer">
        <div>Buy our product now!</div>
      </div>
      <div data-lyrics-container="true">
        [Verse 2]<br>
        Second container line 1<br>
        Second container line 2<br>
      </div>
      <div class="LyricsFooter">
        <span>325 Embed</span>
      </div>
    </body>
    </html>
    """
    containers = _extract_container_contents(sample_html)
    assert len(containers) == 2, f"Expected 2 containers, extracted {len(containers)}"

    parsed = _parse_lyrics_page(sample_html)
    assert parsed is not None
    assert "Deep nested verse line 1" in parsed
    assert "Deep nested verse line 2" in parsed
    assert "Second container line 1" in parsed
    assert "Second container line 2" in parsed
    assert "42 Contributors" not in parsed
    assert "Translations" not in parsed
    assert "Buy our product" not in parsed
    assert "Embed" not in parsed

    print("  [PASS] Depth tracking successfully parsed all nested divs and excluded all ads & badges.")


async def run_all():
    print("=" * 60)
    print("      LYRICA — REAL GENIUS INTEGRATION TEST SUITE")
    print("=" * 60)
    test_parser_adversarial_nested_html()
    await test_live_the_weeknd()
    await test_live_queen()
    print("\n" + "=" * 60)
    print("  ALL REAL GENIUS INTEGRATION TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all())

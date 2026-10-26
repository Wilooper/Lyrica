"""
Test Genius Fetcher HTML parsing logic
"""
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.sources.genius_fetcher import (
    _extract_container_contents,
    _html_to_text,
    _clean,
    _parse_lyrics_page,
)

SAMPLE_GENIUS_HTML_MULTI_CONTAINER = '''
<html>
<body>
<div data-lyrics-container="true" class="Lyrics__Container-sc-1ynbvbe-1">
[Verse 1]<br>
Yeah, I've been trying to call<br>
<div>
    <a href="/annotations/123"><span>I've been on my own for long enough</span></a>
</div>
<span data-exclude-from-selection="true">14 Contributors</span>
Maybe you can show me how to love, maybe<br>
</div>
<div class="InBetweenAd">Some Advertisement Content That Must Be Ignored</div>
<div data-lyrics-container="true" class="Lyrics__Container-sc-1ynbvbe-1">
[Chorus]<br>
I said, ooh, I'm blinded by the lights<br>
No, I can't sleep until I feel your touch<br>
</div>
<div class="LyricsFooter">150 Embed</div>
</body>
</html>
'''

def test_extract_containers():
    containers = _extract_container_contents(SAMPLE_GENIUS_HTML_MULTI_CONTAINER)
    assert len(containers) == 2, f"Expected 2 containers, got {len(containers)}"
    # Verify depth tracking captured inner div
    assert "I've been on my own for long enough" in containers[0]
    assert "Maybe you can show me how to love" in containers[0]

def test_parse_lyrics_page():
    parsed = _parse_lyrics_page(SAMPLE_GENIUS_HTML_MULTI_CONTAINER)
    assert parsed is not None
    assert "[Verse 1]" in parsed
    assert "Yeah, I've been trying to call" in parsed
    assert "I've been on my own for long enough" in parsed
    assert "Maybe you can show me how to love, maybe" in parsed
    assert "[Chorus]" in parsed
    assert "I said, ooh, I'm blinded by the lights" in parsed
    # Verify exclusion
    assert "14 Contributors" not in parsed
    assert "Some Advertisement Content" not in parsed
    assert "Embed" not in parsed
    print("All assertions in test_parse_lyrics_page passed!")

if __name__ == "__main__":
    test_extract_containers()
    test_parse_lyrics_page()
    print("=== GENIUS HTML PARSER TESTS PASSED! ===")

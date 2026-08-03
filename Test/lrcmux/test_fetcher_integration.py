import asyncio
import sys
import os

# Adjust import path to root
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.sources.lrcmux_fetcher import LrcmuxFetcher

async def test_fetcher():
    fetcher = LrcmuxFetcher()
    
    print("Testing LrcmuxFetcher integration...")
    
    # 1. Test Line Synced Lyrics (Cheema Y - Jackpot)
    print("\n--- Test 1: Cheema Y - Jackpot (timestamps=True) ---")
    res = await fetcher.fetch("Cheema Y", "Jackpot", timestamps=True)
    if not res:
        print("Failed to fetch Cheema Y - Jackpot")
        sys.exit(1)
        
    print(f"Status: SUCCESS")
    print(f"Source: {res.get('source')}")
    print(f"Artist: {res.get('artist')}")
    print(f"Title: {res.get('title')}")
    print(f"Has Timestamps: {res.get('hasTimestamps')}")
    print(f"Timed Lyrics Length: {len(res.get('timed_lyrics', []))}")
    print("First line:", res.get('timed_lyrics')[0] if res.get('timed_lyrics') else "None")
    
    # Assertions
    assert res.get('source') == 'lrcmux'
    assert res.get('artist').lower() == 'cheema y'
    assert res.get('title').lower() == 'jackpot'
    assert res.get('hasTimestamps') is True
    assert len(res.get('timed_lyrics', [])) > 0

    # 2. Test Word Level Synced Lyrics (Rick Astley - Never Gonna Give You Up)
    print("\n--- Test 2: Rick Astley - Never Gonna Give You Up (timestamps=True, word_level=True) ---")
    res = await fetcher.fetch("Rick Astley", "Never Gonna Give You Up", timestamps=True, word_level=True)
    if not res:
        print("Failed to fetch Rick Astley - Never Gonna Give You Up")
        sys.exit(1)
        
    print(f"Status: SUCCESS")
    print(f"Source: {res.get('source')}")
    print(f"Artist: {res.get('artist')}")
    print(f"Title: {res.get('title')}")
    print(f"Has Timestamps: {res.get('hasTimestamps')}")
    print(f"Timed Lyrics Length: {len(res.get('timed_lyrics', []))}")
    
    # Assertions
    assert res.get('source') == 'lrcmux'
    assert res.get('hasTimestamps') is True
    assert len(res.get('timed_lyrics', [])) > 0
    
    # Check that word-level sync ('words' key) is parsed and present
    has_words = any("words" in line for line in res.get('timed_lyrics', []))
    assert has_words, "Expected word-level sync data to be parsed into 'words' key"
    
    # Verify that we keep raw word level info or structure correctly (lines returned by fetcher have timestamps)
    print("First line:", res.get('timed_lyrics')[0] if res.get('timed_lyrics') else "None")
    # Print the line that has words
    sample_word_line = next(line for line in res.get('timed_lyrics', []) if "words" in line)
    print("Sample line with words:", sample_word_line)

    # 3. Test Nonexistent Song
    print("\n--- Test 3: Nonexistent Song ---")
    res = await fetcher.fetch("Rick Astley Nonexistent Artist", "Never Gonna Give You Up Nonexistent Song", timestamps=True)
    print("Result:", res)
    assert res is None, f"Expected None for nonexistent song, got {res}"
    
    print("\nAll fetcher integration tests passed successfully!")

if __name__ == "__main__":
    asyncio.run(test_fetcher())

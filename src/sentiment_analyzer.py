"""
Lyrica API — Sentiment Analyzer
================================
Analyses mood/sentiment of lyrics using TextBlob's pattern-based sentiment
analyser — which does NOT require any NLTK/TextBlob corpus downloads.

The old `blob.tags` (POS tagging) call used the `averaged_perceptron_tagger`
NLTK corpus, which is not present on a fresh Render deployment and cannot be
auto-downloaded at runtime. This rewrite replaces that call with a simple
regex-based word extraction that has zero external data dependencies.
"""

from textblob import TextBlob
import re
from src.logger import get_logger

logger = get_logger("sentiment_analyzer")


# ─────────────────────────────────────────────────────────────────────────────
# Lyrics extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_lyrics_text(result: dict) -> str:
    """Extract plain text lyrics from a fetcher result dict."""
    lyrics_text = (
        result.get("lyrics") or
        result.get("plain_lyrics") or
        result.get("lyrics_text") or
        result.get("lyric") or
        result.get("text") or
        ""
    )

    # Handle timed_lyrics: list of {text, start_time, ...}
    if isinstance(result.get("timed_lyrics"), list):
        lyrics_text = " ".join(
            item.get("text", "") for item in result["timed_lyrics"]
        )
    elif isinstance(result.get("timed_lyrics"), dict):
        lyrics_text = " ".join(result["timed_lyrics"].values())

    # Strip LRC timestamp brackets like [00:05.84]
    lyrics_text = re.sub(r"\[\d{2}:\d{2}[.:]\d{2,3}\]", "", str(lyrics_text))

    return lyrics_text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Sentiment analysis — uses TextBlob pattern analyser (no corpus needed)
# ─────────────────────────────────────────────────────────────────────────────

def analyze_sentiment(lyrics_text: str) -> dict:
    """
    Analyse sentiment using TextBlob's pattern-based analyser.

    TextBlob's .sentiment property uses the `pattern` library internally,
    NOT NLTK — so it works on Render without any corpus downloads.

    Returns:
        polarity      float  -1 (very negative) to +1 (very positive)
        subjectivity  float   0 (objective) to 1 (subjective)
        mood          str    Positive / Negative / Neutral
        mood_strength str    Very Strong / Strong / Moderate / Weak
        overall_mood  str    descriptive label
    """
    if not lyrics_text or len(lyrics_text.strip()) < 10:
        return {
            "polarity":     0.0,
            "subjectivity": 0.0,
            "mood":         "Unknown",
            "mood_strength": "Insufficient data",
            "overall_mood": "Not enough lyrics to analyze",
        }

    try:
        blob = TextBlob(lyrics_text)
        polarity     = blob.sentiment.polarity
        subjectivity = blob.sentiment.subjectivity

        if polarity > 0.1:
            mood = "Positive"
        elif polarity < -0.1:
            mood = "Negative"
        else:
            mood = "Neutral"

        abs_p = abs(polarity)
        if abs_p > 0.7:    mood_strength = "Very Strong"
        elif abs_p > 0.5:  mood_strength = "Strong"
        elif abs_p > 0.25: mood_strength = "Moderate"
        else:              mood_strength = "Weak"

        return {
            "polarity":      round(polarity, 3),
            "subjectivity":  round(subjectivity, 3),
            "mood":          mood,
            "mood_strength": mood_strength,
            "overall_mood":  _mood_label(polarity, subjectivity),
        }

    except Exception as e:
        logger.error(f"Sentiment analysis error: {e}")
        return {
            "polarity":     0.0,
            "subjectivity": 0.0,
            "mood":         "Unknown",
            "mood_strength": "Error",
            "overall_mood": f"Analysis failed: {e}",
        }


def _mood_label(polarity: float, subjectivity: float) -> str:
    if polarity > 0.5:
        return "Very Happy & Emotional" if subjectivity > 0.6 else (
            "Happy & Expressive" if subjectivity > 0.3 else "Uplifting & Positive")
    elif polarity > 0.25:
        return "Joyful & Personal" if subjectivity > 0.6 else (
            "Cheerful" if subjectivity > 0.3 else "Optimistic")
    elif polarity > 0.1:
        return "Mildly Positive"
    elif polarity > -0.1:
        return "Introspective & Neutral" if subjectivity > 0.6 else (
            "Matter-of-fact" if subjectivity > 0.3 else "Neutral & Objective")
    elif polarity > -0.25:
        return "Mildly Negative"
    elif polarity > -0.5:
        return "Sad & Emotional" if subjectivity > 0.6 else (
            "Melancholic" if subjectivity > 0.3 else "Dark")
    else:
        return "Very Sad & Emotional" if subjectivity > 0.6 else (
            "Angry & Intense" if subjectivity > 0.3 else "Very Negative & Harsh")


# ─────────────────────────────────────────────────────────────────────────────
# Word frequency — corpus-free implementation
# ─────────────────────────────────────────────────────────────────────────────

# Common English stop words — no external data needed
_STOP_WORDS = {
    "i","me","my","myself","we","our","ours","ourselves","you","your","yours",
    "yourself","he","him","his","himself","she","her","hers","herself","it",
    "its","itself","they","them","their","theirs","themselves","what","which",
    "who","whom","this","that","these","those","am","is","are","was","were",
    "be","been","being","have","has","had","having","do","does","did","doing",
    "a","an","the","and","but","if","or","because","as","until","while","of",
    "at","by","for","with","about","against","between","into","through",
    "during","before","after","above","below","to","from","up","down","in",
    "out","on","off","over","under","again","further","then","once","here",
    "there","when","where","why","how","all","both","each","few","more",
    "most","other","some","such","no","nor","not","only","own","same","so",
    "than","too","very","s","t","can","will","just","don","should","now",
    "d","ll","m","o","re","ve","y","ain","couldn","didn","doesn","hadn",
    "hasn","haven","isn","ma","mightn","mustn","needn","shan","shouldn",
    "wasn","weren","won","wouldn","na","gonna","wanna","gotta","yeah","oh",
    "uh","ooh","mm","la","da","hey","ya","em","cause","til","let","like",
}


def analyze_word_frequency(lyrics_text: str, top_n: int = 10) -> dict:
    """
    Extract sentiment-carrying words from lyrics WITHOUT using NLTK corpus.

    Strategy:
    1. Tokenise with a simple regex (no POS tagger needed)
    2. Skip stop words and very short tokens
    3. Score each word with TextBlob's pattern-based sentiment
       (this is a simple lexicon lookup — no corpus download required)
    4. Return top positive and negative words by frequency

    Returns:
        {
            "positive_words": [{"word": str, "frequency": int}, ...],
            "negative_words": [{"word": str, "frequency": int}, ...],
        }
    """
    if not lyrics_text:
        return {"positive_words": [], "negative_words": []}

    try:
        # Simple word tokenisation: keep only alphabetic tokens, 3+ chars
        words = re.findall(r"\b[a-zA-Z]{3,}\b", lyrics_text.lower())
        # Filter stop words
        words = [w for w in words if w not in _STOP_WORDS]

        positive_words: dict[str, int] = {}
        negative_words: dict[str, int] = {}

        # Use a set to avoid scoring the same word multiple times
        seen_scores: dict[str, float] = {}

        for word in words:
            if word not in seen_scores:
                try:
                    # TextBlob pattern sentiment — pure lexicon, no corpus
                    seen_scores[word] = TextBlob(word).sentiment.polarity
                except Exception:
                    seen_scores[word] = 0.0

            polarity = seen_scores[word]
            if polarity > 0.1:
                positive_words[word] = positive_words.get(word, 0) + 1
            elif polarity < -0.1:
                negative_words[word] = negative_words.get(word, 0) + 1

        top_pos = sorted(positive_words.items(), key=lambda x: x[1], reverse=True)[:top_n]
        top_neg = sorted(negative_words.items(), key=lambda x: x[1], reverse=True)[:top_n]

        return {
            "positive_words": [{"word": w, "frequency": f} for w, f in top_pos],
            "negative_words": [{"word": w, "frequency": f} for w, f in top_neg],
        }

    except Exception as e:
        logger.error(f"Word frequency analysis error: {e}")
        return {"positive_words": [], "negative_words": []}

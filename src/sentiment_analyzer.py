from textblob import TextBlob
from src.logger import get_logger
from typing import Optional

logger = get_logger("sentiment_analyzer")

def extract_lyrics_text(result: dict) -> str:
    """
    Extract lyrics text from different fetcher formats.
    
    Different APIs return lyrics in different fields:
    - lyrics, plain_lyrics, lyrics_text, timed_lyrics, etc.
    """
    lyrics_text = (
        result.get("lyrics") or
        result.get("plain_lyrics") or
        result.get("lyrics_text") or
        result.get("lyric") or
        result.get("text") or
        ""
    )
    
    # If timed_lyrics (dict with timestamps), extract just the text
    if isinstance(result.get("timed_lyrics"), dict):
        lyrics_text = " ".join(result["timed_lyrics"].values())
    elif isinstance(result.get("timed_lyrics"), list):
        # List of dicts with 'text' key
        lyrics_text = " ".join([item.get("text", "") for item in result["timed_lyrics"]])
    
    return str(lyrics_text).strip()

def analyze_sentiment(lyrics_text: str) -> dict:
    """
    Analyze sentiment/mood of lyrics using TextBlob.
    
    Returns:
        {
            "polarity": float (-1 to 1),
            "subjectivity": float (0 to 1),
            "mood": str (Positive/Negative/Neutral),
            "mood_strength": str (Very Strong/Strong/Moderate/Weak),
            "overall_mood": str (descriptive mood)
        }
    """
    
    if not lyrics_text or len(lyrics_text.strip()) < 10:
        return {
            "polarity": 0.0,
            "subjectivity": 0.0,
            "mood": "Unknown",
            "mood_strength": "Insufficient data",
            "overall_mood": "Not enough lyrics to analyze"
        }
    
    try:
        blob = TextBlob(lyrics_text)
        polarity = blob.sentiment.polarity  # -1 (negative) to 1 (positive)
        subjectivity = blob.sentiment.subjectivity  # 0 (objective) to 1 (subjective)
        
        # Determine mood based on polarity
        if polarity > 0.1:
            mood = "Positive"
        elif polarity < -0.1:
            mood = "Negative"
        else:
            mood = "Neutral"
        
        # Determine mood strength based on absolute polarity
        abs_polarity = abs(polarity)
        if abs_polarity > 0.7:
            mood_strength = "Very Strong"
        elif abs_polarity > 0.5:
            mood_strength = "Strong"
        elif abs_polarity > 0.25:
            mood_strength = "Moderate"
        else:
            mood_strength = "Weak"
        
        # Generate descriptive overall mood
        overall_mood = generate_mood_description(polarity, subjectivity)
        
        logger.info(f"Sentiment analysis: {mood} ({polarity:.2f}), Subjectivity: {subjectivity:.2f}")
        
        return {
            "polarity": round(polarity, 3),
            "subjectivity": round(subjectivity, 3),
            "mood": mood,
            "mood_strength": mood_strength,
            "overall_mood": overall_mood
        }
    
    except Exception as e:
        logger.error(f"Sentiment analysis error: {str(e)}")
        return {
            "polarity": 0.0,
            "subjectivity": 0.0,
            "mood": "Unknown",
            "mood_strength": "Error",
            "overall_mood": f"Analysis failed: {str(e)}"
        }

def generate_mood_description(polarity: float, subjectivity: float) -> str:
    """
    Generate a descriptive mood label based on polarity and subjectivity.
    """
    
    # Mood mapping based on polarity and subjectivity
    if polarity > 0.5:
        if subjectivity > 0.6:
            return "Very Happy & Emotional"
        elif subjectivity > 0.3:
            return "Happy & Expressive"
        else:
            return "Uplifting & Positive"
    
    elif polarity > 0.25:
        if subjectivity > 0.6:
            return "Joyful & Personal"
        elif subjectivity > 0.3:
            return "Cheerful"
        else:
            return "Optimistic"
    
    elif polarity > 0.1:
        return "Mildly Positive"
    
    elif polarity > -0.1:
        if subjectivity > 0.6:
            return "Introspective & Neutral"
        elif subjectivity > 0.3:
            return "Matter-of-fact"
        else:
            return "Neutral & Objective"
    
    elif polarity > -0.25:
        return "Mildly Negative"
    
    elif polarity > -0.5:
        if subjectivity > 0.6:
            return "Sad & Emotional"
        elif subjectivity > 0.3:
            return "Melancholic"
        else:
            return "Dark"
    
    else:
        if subjectivity > 0.6:
            return "Very Sad & Emotional"
        elif subjectivity > 0.3:
            return "Angry & Intense"
        else:
            return "Very Negative & Harsh"

def analyze_word_frequency(lyrics_text: str, top_n: int = 10) -> dict:
    """
    Extract top sentiment words from lyrics.
    
    Returns:
        {
            "positive_words": [list of positive words with frequency],
            "negative_words": [list of negative words with frequency]
        }
    """
    
    if not lyrics_text:
        return {"positive_words": [], "negative_words": []}
    
    try:
        blob = TextBlob(lyrics_text)
        words = [word.lower() for word, pos in blob.tags if pos == 'NN' or pos == 'JJ']
        
        positive_words = {}
        negative_words = {}
        
        for word in words:
            word_blob = TextBlob(word)
            polarity = word_blob.sentiment.polarity
            
            if polarity > 0.1:
                positive_words[word] = positive_words.get(word, 0) + 1
            elif polarity < -0.1:
                negative_words[word] = negative_words.get(word, 0) + 1
        
        # Sort and get top N
        top_positive = sorted(positive_words.items(), key=lambda x: x[1], reverse=True)[:top_n]
        top_negative = sorted(negative_words.items(), key=lambda x: x[1], reverse=True)[:top_n]
        
        return {
            "positive_words": [{"word": w, "frequency": f} for w, f in top_positive],
            "negative_words": [{"word": w, "frequency": f} for w, f in top_negative]
        }
    
    except Exception as e:
        logger.error(f"Word frequency analysis error: {str(e)}")
        return {"positive_words": [], "negative_words": []}

// DOM Elements
const form = document.getElementById('lyrics-form');
const artistInput = document.getElementById('artist');
const songInput = document.getElementById('song');
const timestampsCheckbox = document.getElementById('timestamps');
const resultsSection = document.getElementById('results');
const loadingSection = document.getElementById('loading');
const errorSection = document.getElementById('error');
const resultsTitle = document.getElementById('results-title');
const sourceBadge = document.getElementById('source-badge');
const timestampSpan = document.getElementById('timestamp');
const lyricsContent = document.getElementById('lyrics-content');
const karaokeControls = document.getElementById('karaoke-controls');
const karaokeToggle = document.getElementById('karaoke-toggle');
const downloadButton = document.getElementById('download-lyrics');
const progressFill = document.querySelector('.progress-fill');
const errorMessage = document.getElementById('error-message');

// Karaoke state
let karaokeMode = false;
let currentLyrics = null;
let karaokeInterval = null;
let startTime = null;

// API Configuration
const API_BASE_URL = 'http://127.0.0.1:9999';

// Event Listeners
form.addEventListener('submit', handleSearch);
karaokeToggle.addEventListener('click', toggleKaraoke);
downloadButton.addEventListener('click', handleDownload);
// Download functionality
function handleDownload() {
    if (!currentLyrics) return;

    const artist = currentLyrics.artist;
    const title = currentLyrics.title;
    let content = '';
    let filename = '';

    if (currentLyrics.timed_lyrics && currentLyrics.hasTimestamps) {
        // Create LRC format content
        content = generateLRCContent(currentLyrics.timed_lyrics);
        filename = `${artist} - ${title}.lrc`;
    } else {
        // Create plain text content
        content = currentLyrics.lyrics;
        filename = `${artist} - ${title}.txt`;
    }

    // Create and trigger download
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

function generateLRCContent(timedLyrics) {
    let lrcContent = '';
    
    // Add metadata
    lrcContent += `[ar:${currentLyrics.artist}]\n`;
    lrcContent += `[ti:${currentLyrics.title}]\n`;
    lrcContent += `[length:${formatTime(timedLyrics[timedLyrics.length - 1].end_time)}]\n`;
    lrcContent += `[source:${currentLyrics.source}]\n\n`;

    // Add timed lyrics
    timedLyrics.forEach(line => {
        const timeTag = formatLRCTime(line.start_time);
        lrcContent += `[${timeTag}]${line.text}\n`;
    });

    return lrcContent;
}

function formatLRCTime(ms) {
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    const milliseconds = ms % 1000;
    const centiseconds = Math.floor(milliseconds / 10);

    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(centiseconds).padStart(2, '0')}`;
}

function formatTime(ms) {
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

// Smooth scrolling for navigation links
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const targetId = link.getAttribute('href');
        const targetElement = document.querySelector(targetId);
        if (targetElement) {
            targetElement.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Search functionality
async function handleSearch(e) {
    e.preventDefault();
    
    const artist = artistInput.value.trim();
    const song = songInput.value.trim();
    const timestamps = timestampsCheckbox.checked;
    
    if (!artist || !song) {
        showError('Please enter both artist and song name');
        return;
    }
    
    showLoading();
    hideError();
    hideResults();
    
    try {
        const response = await fetch(`${API_BASE_URL}/lyrics/?artist=${encodeURIComponent(artist)}&song=${encodeURIComponent(song)}&timestamps=${timestamps}`);
        const data = await response.json();
        
        hideLoading();
        
        if (data.status === 'success') {
            displayResults(data.data);
        } else {
            showError(data.error.message || 'Failed to fetch lyrics');
        }
    } catch (error) {
        hideLoading();
        showError('Failed to connect to the API. Make sure the Lyrica server is running on port 9999.');
        console.error('API Error:', error);
    }
}

// Display search results
function displayResults(data) {
    currentLyrics = data;
    
    // Update results header
    resultsTitle.textContent = `${data.artist} - ${data.title}`;
    sourceBadge.textContent = data.source.replace('_', ' ').toUpperCase();
    timestampSpan.textContent = `Found at ${data.timestamp}`;
    
    // Display lyrics
    if (data.timed_lyrics && data.hasTimestamps) {
        displayTimedLyrics(data.timed_lyrics);
        showKaraokeControls();
    } else {
        displayPlainLyrics(data.lyrics);
        hideKaraokeControls();
    }
    
    showResults();
    
    // Scroll to results
    resultsSection.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
    });
}

// Display plain lyrics
function displayPlainLyrics(lyrics) {
    lyricsContent.className = 'lyrics-content';
    lyricsContent.textContent = lyrics;
}

// Display timed lyrics
function displayTimedLyrics(timedLyrics) {
    lyricsContent.className = 'lyrics-content';
    lyricsContent.innerHTML = '';
    
    timedLyrics.forEach((line, index) => {
        const lineElement = document.createElement('div');
        lineElement.className = 'lyrics-line';
        lineElement.textContent = line.text;
        lineElement.dataset.startTime = line.start_time;
        lineElement.dataset.endTime = line.end_time;
        lineElement.dataset.index = index;
        lyricsContent.appendChild(lineElement);
    });
}

// Karaoke functionality
function toggleKaraoke() {
    if (!currentLyrics || !currentLyrics.timed_lyrics) {
        return;
    }
    
    karaokeMode = !karaokeMode;
    
    if (karaokeMode) {
        startKaraoke();
    } else {
        stopKaraoke();
    }
}

function startKaraoke() {
    karaokeToggle.innerHTML = '<i class="fas fa-pause"></i> Pause Karaoke';
    karaokeToggle.classList.add('playing');
    lyricsContent.classList.add('karaoke-mode');
    
    startTime = Date.now();
    updateKaraoke();
    
    karaokeInterval = setInterval(updateKaraoke, 100);
}

function stopKaraoke() {
    karaokeToggle.innerHTML = '<i class="fas fa-play"></i> Start Karaoke Mode';
    karaokeToggle.classList.remove('playing');
    lyricsContent.classList.remove('karaoke-mode');
    
    if (karaokeInterval) {
        clearInterval(karaokeInterval);
        karaokeInterval = null;
    }
    
    // Remove active class from all lines
    document.querySelectorAll('.lyrics-line').forEach(line => {
        line.classList.remove('active');
    });
    
    progressFill.style.width = '0%';
}

function updateKaraoke() {
    if (!karaokeMode || !currentLyrics || !currentLyrics.timed_lyrics) {
        return;
    }
    
    const currentTime = Date.now() - startTime;
    const lines = document.querySelectorAll('.lyrics-line');
    let activeLineFound = false;
    
    lines.forEach(line => {
        const startTime = parseInt(line.dataset.startTime);
        const endTime = parseInt(line.dataset.endTime);
        
        if (currentTime >= startTime && currentTime <= endTime) {
            line.classList.add('active');
            activeLineFound = true;
            
            // Scroll to active line
            line.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });
            
            // Update progress bar
            const progress = Math.min(100, (currentTime / endTime) * 100);
            progressFill.style.width = `${progress}%`;
        } else {
            line.classList.remove('active');
        }
    });
    
    // If no active line, update progress based on total duration
    if (!activeLineFound && currentLyrics.timed_lyrics.length > 0) {
        const totalDuration = currentLyrics.timed_lyrics[currentLyrics.timed_lyrics.length - 1].end_time;
        const progress = Math.min(100, (currentTime / totalDuration) * 100);
        progressFill.style.width = `${progress}%`;
        
        // Stop karaoke if we've reached the end
        if (progress >= 100) {
            stopKaraoke();
        }
    }
}

// UI Helper Functions
function showLoading() {
    loadingSection.classList.remove('hidden');
}

function hideLoading() {
    loadingSection.classList.add('hidden');
}

function showResults() {
    resultsSection.classList.remove('hidden');
}

function hideResults() {
    resultsSection.classList.add('hidden');
}

function showError(message) {
    errorMessage.textContent = message;
    errorSection.classList.remove('hidden');
}

function hideError() {
    errorSection.classList.add('hidden');
}

function showKaraokeControls() {
    karaokeControls.classList.remove('hidden');
}

function hideKaraokeControls() {
    karaokeControls.classList.add('hidden');
}

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    // Add some sample suggestions
    const sampleSongs = [
        { artist: 'Arijit Singh', song: 'Tum Hi Ho' },
        { artist: 'Yo Yo Honey Singh', song: 'Blue Eyes' },
        { artist: 'Rahat Fateh Ali Khan', song: 'Jag Ghoomeya' },
        { artist: 'Shreya Ghoshal', song: 'Teri Ore' }
    ];
    
    // Add click handlers to sample songs (you can implement this later)
    console.log('Lyrica Music Site Loaded!');
    console.log('Sample songs you can try:', sampleSongs);
});

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Space bar to toggle karaoke
    if (e.code === 'Space' && karaokeMode && currentLyrics && currentLyrics.timed_lyrics) {
        e.preventDefault();
        toggleKaraoke();
    }
    
    // Enter to search when focused on form inputs
    if (e.code === 'Enter' && (e.target === artistInput || e.target === songInput)) {
        e.preventDefault();
        form.dispatchEvent(new Event('submit'));
    }
});

// Add visual feedback for form interactions
artistInput.addEventListener('input', function() {
    if (this.value.trim()) {
        this.classList.add('has-value');
    } else {
        this.classList.remove('has-value');
    }
});

songInput.addEventListener('input', function() {
    if (this.value.trim()) {
        this.classList.add('has-value');
    } else {
        this.classList.remove('has-value');
    }
});

// Auto-focus on artist input when page loads
window.addEventListener('load', function() {
    artistInput.focus();
});

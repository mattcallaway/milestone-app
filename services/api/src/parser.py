"""Media filename parser for TV shows, movies, and audiobooks."""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedMedia:
    """Parsed media information from filename."""
    type: str  # 'movie', 'tv_episode', 'audiobook', 'unknown'
    title: Optional[str] = None
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    

# TV show patterns (order matters - more specific first)
TV_PATTERNS = [
    # S01E02, s01e02
    re.compile(r'(.+?)[.\s_-]+[Ss](\d{1,2})[Ee](\d{1,2})', re.IGNORECASE),
    # 1x02, 01x02
    re.compile(r'(.+?)[.\s_-]+(\d{1,2})x(\d{1,2})', re.IGNORECASE),
    # Season 1 Episode 2
    re.compile(r'(.+?)[.\s_-]+Season\s*(\d{1,2})\s*Episode\s*(\d{1,2})', re.IGNORECASE),
    # S01.E02, S01-E02
    re.compile(r'(.+?)[.\s_-]+[Ss](\d{1,2})[.\s_-]*[Ee](\d{1,2})', re.IGNORECASE),
]

# Movie patterns
MOVIE_PATTERNS = [
    # Movie Name (2020)
    re.compile(r'(.+?)\s*\((\d{4})\)'),
    # Movie.Name.2020
    re.compile(r'(.+?)[.\s_-]+(\d{4})(?:[.\s_-]|$)'),
]

# Common video extensions
VIDEO_EXTENSIONS = {
    'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 
    'm4v', 'mpg', 'mpeg', 'ts', 'm2ts', 'vob'
}

# Common audio extensions
AUDIO_EXTENSIONS = {
    'mp3', 'm4a', 'm4b', 'flac', 'ogg', 'opus', 'wma',
    'aac', 'wav', 'alac', 'aiff', 'ape'
}

# All recognized media extensions
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

# Folder names that indicate audiobook content
AUDIOBOOK_FOLDER_HINTS = {'audiobooks', 'audiobook'}


def clean_title(title: str) -> str:
    """Clean up extracted title."""
    # Replace dots, underscores with spaces
    title = re.sub(r'[._]', ' ', title)
    # Remove extra whitespace
    title = ' '.join(title.split())
    # Capitalize words
    title = title.title()
    return title.strip()


def parse_filename(filename: str) -> ParsedMedia:
    """
    Parse a media filename to extract type, title, year, season, episode.
    
    Examples:
        "Breaking.Bad.S01E02.720p.mkv" -> TV, "Breaking Bad", season=1, episode=2
        "The Matrix (1999).mp4" -> Movie, "The Matrix", year=1999
    """
    # Remove extension
    name = re.sub(r'\.[^.]+$', '', filename)
    
    # Try TV patterns first
    for pattern in TV_PATTERNS:
        match = pattern.match(name)
        if match:
            title = clean_title(match.group(1))
            season = int(match.group(2))
            episode = int(match.group(3))
            return ParsedMedia(
                type='tv_episode',
                title=title,
                season=season,
                episode=episode
            )
    
    # Try movie patterns
    for pattern in MOVIE_PATTERNS:
        match = pattern.match(name)
        if match:
            title = clean_title(match.group(1))
            year = int(match.group(2))
            # Sanity check year
            if 1900 <= year <= 2100:
                return ParsedMedia(
                    type='movie',
                    title=title,
                    year=year
                )
    
    # Unknown - just use cleaned filename as title
    return ParsedMedia(
        type='unknown',
        title=clean_title(name)
    )


def parse_path(filepath: str) -> ParsedMedia:
    """
    Parse a full file path, using both filename and directory hints.
    
    Detection priority:
    1. Filename patterns (TV episodes via S01E02, movies via year)
    2. Parent directory hints (Season folders, Audiobooks folder)
    3. File extension hints (.m4b is almost always an audiobook)
    """
    from pathlib import Path
    
    path = Path(filepath)
    filename = path.name
    ext = path.suffix.lstrip('.').lower()
    
    # Collect parent directory names for hint matching
    parent_names_lower = [p.name.lower() for p in path.parents if p.name]
    
    # Check if any parent directory indicates audiobook content
    is_in_audiobook_dir = any(
        name in AUDIOBOOK_FOLDER_HINTS for name in parent_names_lower
    )
    
    # If file is audio AND in an audiobook directory, classify as audiobook
    if ext in AUDIO_EXTENSIONS and is_in_audiobook_dir:
        return ParsedMedia(
            type='audiobook',
            title=clean_title(re.sub(r'\.[^.]+$', '', filename))
        )
    
    # .m4b files are audiobooks by convention, even without folder hints
    if ext == 'm4b':
        return ParsedMedia(
            type='audiobook',
            title=clean_title(re.sub(r'\.[^.]+$', '', filename))
        )
    
    # First try parsing the filename (TV / movie patterns)
    result = parse_filename(filename)
    
    # If unknown, try to get hints from parent directories
    if result.type == 'unknown':
        # Check if parent folder looks like a season folder
        parent_name = path.parent.name.lower()
        season_match = re.match(r'season\s*(\d+)', parent_name, re.IGNORECASE)
        if season_match:
            result.season = int(season_match.group(1))
            result.type = 'tv_episode'
            # Try to get show name from grandparent
            if path.parent.parent.name:
                result.title = clean_title(path.parent.parent.name)
    
    return result


def is_video_file(filepath: str) -> bool:
    """Check if file is a video based on extension."""
    ext = filepath.rsplit('.', 1)[-1].lower() if '.' in filepath else ''
    return ext in VIDEO_EXTENSIONS


def is_audio_file(filepath: str) -> bool:
    """Check if file is an audio file based on extension."""
    ext = filepath.rsplit('.', 1)[-1].lower() if '.' in filepath else ''
    return ext in AUDIO_EXTENSIONS


def is_media_file(filepath: str) -> bool:
    """Check if file is any recognized media type (video or audio)."""
    ext = filepath.rsplit('.', 1)[-1].lower() if '.' in filepath else ''
    return ext in MEDIA_EXTENSIONS

"""
Utility functions for the JioSaavn Telegram Bot.
Handles file operations, metadata embedding, and image processing.
"""
import os
import re
import hashlib
import tempfile
import logging
from typing import Dict, Optional, Tuple, Union
from pathlib import Path

import requests
from PIL import Image, UnidentifiedImageError
import io

import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TYER, TCON, APIC, COMM, TRCK, TCOM, TDRC

logger = logging.getLogger(__name__)

def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """
    Sanitize filename by removing invalid characters.
    
    Args:
        filename: Original filename
        max_length: Maximum length of sanitized filename
        
    Returns:
        Sanitized filename safe for filesystem
    """
    # Remove invalid characters
    invalid_chars = r'[<>:"/\\|?*]'
    filename = re.sub(invalid_chars, '', filename)
    
    # Replace multiple spaces with single space
    filename = re.sub(r'\s+', ' ', filename)
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    
    # Truncate if too long
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length - len(ext)] + ext
    
    return filename

def format_duration(seconds: Union[int, float, str]) -> str:
    """
    Format duration in seconds to HH:MM:SS or MM:SS.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string
    """
    try:
        seconds = int(float(seconds))
    except (ValueError, TypeError):
        return "00:00"
    
    if seconds <= 0:
        return "00:00"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"

def format_file_size(bytes_size: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        bytes_size: Size in bytes
        
    Returns:
        Human-readable file size
    """
    if bytes_size < 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(bytes_size)
    
    for unit in units:
        if size < 1024.0 or unit == 'TB':
            return f"{size:.2f} {unit}"
        size /= 1024.0
    
    return f"{size:.2f} TB"

def download_and_process_image(
    image_url: str, 
    identifier: str, 
    max_size: Tuple[int, int] = (500, 500)
) -> Optional[bytes]:
    """
    Download and process image for embedding in MP3 metadata.
    
    Args:
        image_url: URL of the image
        identifier: Unique identifier for caching/logging
        max_size: Maximum dimensions for the image
        
    Returns:
        Image bytes in JPEG format or None if failed
    """
    try:
        logger.info(f"Downloading image: {image_url[:50]}...")
        
        # Download image
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(image_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Open and process image
        img = Image.open(io.BytesIO(response.content))
        
        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            
            if img.mode == 'P':
                img = img.convert('RGBA')
            
            # Paste image on background
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize if too large
        if img.width > max_size[0] or img.height > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Convert to bytes
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=90, optimize=True)
        img_bytes = img_byte_arr.getvalue()
        
        logger.debug(f"Image processed: {len(img_bytes)} bytes")
        return img_bytes
        
    except UnidentifiedImageError:
        logger.error(f"Invalid image format: {image_url}")
    except requests.RequestException as e:
        logger.error(f"Failed to download image: {e}")
    except Exception as e:
        logger.error(f"Image processing error: {e}")
    
    return None

def embed_metadata_to_mp3(
    mp3_path: str, 
    metadata: Dict, 
    cover_art_bytes: Optional[bytes] = None
) -> Tuple[bool, str]:
    """
    Embed metadata and cover art into an MP3 file.
    
    Args:
        mp3_path: Path to the MP3 file
        metadata: Dictionary containing song metadata
        cover_art_bytes: JPEG image bytes for cover art
        
    Returns:
        Tuple of (success, message)
    """
    try:
        # Check if file exists
        if not os.path.exists(mp3_path):
            return False, f"File not found: {mp3_path}"
        
        # Load MP3 file
        try:
            audio = MP3(mp3_path, ID3=ID3)
        except mutagen.MutagenError:
            audio = MP3(mp3_path)
        
        # Remove existing tags to start fresh
        if audio.tags:
            audio.tags.clear()
        else:
            audio.add_tags()
        
        # Add title
        if 'title' in metadata and metadata['title']:
            audio.tags.add(TIT2(encoding=3, text=str(metadata['title'])))
        
        # Add artist
        if 'primary_artists' in metadata and metadata['primary_artists']:
            audio.tags.add(TPE1(encoding=3, text=str(metadata['primary_artists'])))
        
        # Add album artist (same as primary or "Various Artists")
        if 'album' in metadata and metadata['album']:
            album_artist = metadata.get('primary_artists', 'Various Artists')
            audio.tags.add(TPE2(encoding=3, text=str(album_artist)))
        
        # Add album
        if 'album' in metadata and metadata['album']:
            audio.tags.add(TALB(encoding=3, text=str(metadata['album'])))
        
        # Add year
        if 'year' in metadata and metadata['year']:
            # Try to parse year from string
            year_str = str(metadata['year'])
            year_match = re.search(r'\b(19|20)\d{2}\b', year_str)
            if year_match:
                audio.tags.add(TYER(encoding=3, text=year_match.group()))
                audio.tags.add(TDRC(encoding=3, text=year_match.group()))
        
        # Add genre/language
        if 'language' in metadata and metadata['language']:
            lang_map = {
                'hindi': 'Hindi', 'tamil': 'Tamil', 'telugu': 'Telugu',
                'malayalam': 'Malayalam', 'kannada': 'Kannada',
                'english': 'English', 'punjabi': 'Punjabi'
            }
            genre = lang_map.get(metadata['language'].lower(), metadata['language'].title())
            audio.tags.add(TCON(encoding=3, text=genre))
        
        # Add comment (store additional info)
        comment_parts = []
        if 'id' in metadata:
            comment_parts.append(f"ID: {metadata['id']}")
        if 'url' in metadata:
            comment_parts.append(f"URL: {metadata['url'][:50]}")
        if 'copyright' in metadata:
            comment_parts.append(f"© {metadata['copyright']}")
        
        comment_text = " | ".join(comment_parts) if comment_parts else "Downloaded via JioSaavn Bot"
        audio.tags.add(COMM(encoding=3, lang='eng', desc='', text=comment_text))
        
        # Add composer (if available)
        if 'music' in metadata and metadata['music']:
            audio.tags.add(TCOM(encoding=3, text=str(metadata['music'])))
        
        # Add cover art
        if cover_art_bytes:
            try:
                audio.tags.add(
                    APIC(
                        encoding=3,  # UTF-8
                        mime='image/jpeg',
                        type=3,  # Front cover
                        desc='Cover',
                        data=cover_art_bytes
                    )
                )
                logger.debug(f"Added cover art: {len(cover_art_bytes)} bytes")
            except Exception as e:
                logger.warning(f"Failed to add cover art: {e}")
        
        # Save metadata
        audio.save(v2_version=3)  # ID3v2.3 for maximum compatibility
        
        # Verify metadata was saved
        audio = MP3(mp3_path, ID3=ID3)
        if audio.tags:
            logger.info(f"Metadata embedded successfully: {metadata.get('title', 'Unknown')}")
            return True, "Metadata embedded successfully"
        else:
            return False, "Failed to save metadata"
        
    except Exception as e:
        logger.error(f"Metadata embedding failed: {e}")
        return False, f"Error: {str(e)}"

def ensure_directory(directory_path: str) -> bool:
    """
    Ensure a directory exists, create if it doesn't.
    
    Args:
        directory_path: Path to directory
        
    Returns:
        True if directory exists or was created
    """
    try:
        Path(directory_path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {directory_path}: {e}")
        return False

def get_file_hash(filepath: str, algorithm: str = 'md5') -> Optional[str]:
    """
    Calculate file hash for caching/verification.
    
    Args:
        filepath: Path to file
        algorithm: Hash algorithm (md5, sha1, sha256)
        
    Returns:
        Hexadecimal hash string or None if failed
    """
    try:
        hash_func = hashlib.new(algorithm)
        
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    except Exception as e:
        logger.error(f"Failed to calculate hash: {e}")
        return None

def cleanup_temp_files(temp_files: list, max_age_hours: int = 24):
    """
    Clean up temporary files older than specified age.
    
    Args:
        temp_files: List of temporary file paths
        max_age_hours: Maximum age in hours before deletion
    """
    import time
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    for filepath in temp_files:
        try:
            if os.path.exists(filepath):
                file_age = current_time - os.path.getmtime(filepath)
                
                if file_age > max_age_seconds:
                    os.remove(filepath)
                    logger.debug(f"Cleaned up old temp file: {filepath}")
        except Exception as e:
            logger.warning(f"Failed to clean up {filepath}: {e}")

def create_temp_file(prefix: str = 'jiosaavn_', suffix: str = '.tmp') -> Optional[str]:
    """
    Create a temporary file with proper permissions.
    
    Args:
        prefix: File prefix
        suffix: File suffix
        
    Returns:
        Path to temporary file or None if failed
    """
    try:
        temp_dir = tempfile.gettempdir()
        ensure_directory(temp_dir)
        
        fd, temp_path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
        os.close(fd)  # Close the file descriptor, we'll open it properly later
        
        # Set permissions (read/write for owner only)
        os.chmod(temp_path, 0o600)
        
        return temp_path
    except Exception as e:
        logger.error(f"Failed to create temp file: {e}")
        return None

def validate_mp3_file(filepath: str) -> Tuple[bool, str]:
    """
    Validate MP3 file integrity and basic properties.
    
    Args:
        filepath: Path to MP3 file
        
    Returns:
        Tuple of (is_valid, message)
    """
    try:
        # Check if file exists
        if not os.path.exists(filepath):
            return False, "File does not exist"
        
        # Check file size
        file_size = os.path.getsize(filepath)
        if file_size < 1024:  # Less than 1KB
            return False, f"File too small: {format_file_size(file_size)}"
        
        if file_size > 100 * 1024 * 1024:  # More than 100MB
            return False, f"File too large: {format_file_size(file_size)}"
        
        # Try to parse MP3 metadata
        try:
            audio = MP3(filepath)
            
            # Check if it has audio properties
            if hasattr(audio, 'info') and audio.info.length > 0:
                duration = format_duration(audio.info.length)
                bitrate = audio.info.bitrate // 1000 if audio.info.bitrate else 0
                
                return True, f"Valid MP3: {duration}, ~{bitrate}kbps, {format_file_size(file_size)}"
            else:
                return False, "Invalid audio properties"
                
        except mutagen.MutagenError:
            # File might be valid MP3 but without ID3 tags
            return True, f"Valid audio file: {format_file_size(file_size)}"
        
    except Exception as e:
        return False, f"Validation error: {str(e)}"

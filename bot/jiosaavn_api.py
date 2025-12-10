"""
JioSaavn API Client for Telegram Bot
Handles all communication with the JioSaavn API.
"""
import requests
import json
import time
from typing import Dict, List, Optional, Union
from urllib.parse import quote
import logging

logger = logging.getLogger(__name__)

class JioSaavnAPI:
    def __init__(self, base_url: str = None):
        """
        Initialize the JioSaavn API client.
        
        Args:
            base_url: Base URL for the API (defaults to your deployed API)
        """
        self.base_url = base_url or "https://jiosaavn-api2.skmassking.workers.dev/api"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.jiosaavn.com/'
        })
        
        # API endpoints based on your structure
        self.endpoints = {
            'search_songs': '/search/songs',
            'search_albums': '/search/albums',
            'search_artists': '/search/artists',
            'search_playlists': '/search/playlists',
            'song': '/song',
            'album': '/album',
            'playlist': '/playlist',
            'artist': '/artist'
        }
    
    def _make_request(self, endpoint: str, params: Dict = None, retries: int = 3) -> Optional[Dict]:
        """
        Make HTTP request to the API with retry logic.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            retries: Number of retry attempts
            
        Returns:
            JSON response as dictionary or None if failed
        """
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(retries):
            try:
                logger.debug(f"API Request: {url} with params {params}")
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                
                # Parse JSON response
                result = response.json()
                
                # Log successful response
                if 'results' in result and result['results']:
                    logger.info(f"API Success: Got {len(result['results'])} results")
                elif 'data' in result and result['data']:
                    logger.info(f"API Success: Got data for {result.get('data', {}).get('name', 'unknown')}")
                
                return result
                
            except requests.exceptions.Timeout:
                logger.warning(f"API Timeout (attempt {attempt + 1}/{retries}): {endpoint}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                continue
                
            except requests.exceptions.RequestException as e:
                logger.error(f"API Request Error: {e}")
                return None
                
            except json.JSONDecodeError as e:
                logger.error(f"API JSON Error: {e}")
                return None
        
        return None
    
    def search_songs(self, query: str, page: int = 1, limit: int = 10) -> Optional[Dict]:
        """
        Search for songs.
        
        Args:
            query: Search query
            page: Page number
            limit: Results per page
            
        Returns:
            Search results or None
        """
        params = {
            'query': query,
            'page': page,
            'limit': limit
        }
        return self._make_request(self.endpoints['search_songs'], params)
    
    def search_albums(self, query: str, page: int = 1, limit: int = 10) -> Optional[Dict]:
        """Search for albums."""
        params = {'query': query, 'page': page, 'limit': limit}
        return self._make_request(self.endpoints['search_albums'], params)
    
    def search_artists(self, query: str, page: int = 1, limit: int = 10) -> Optional[Dict]:
        """Search for artists."""
        params = {'query': query, 'page': page, 'limit': limit}
        return self._make_request(self.endpoints['search_artists'], params)
    
    def search_playlists(self, query: str, page: int = 1, limit: int = 10) -> Optional[Dict]:
        """Search for playlists."""
        params = {'query': query, 'page': page, 'limit': limit}
        return self._make_request(self.endpoints['search_playlists'], params)
    
    def get_song_details(self, song_id: str) -> Optional[Dict]:
        """
        Get detailed information about a song.
        
        Args:
            song_id: Song ID from search results
            
        Returns:
            Song details or None
        """
        params = {'id': song_id}
        return self._make_request(self.endpoints['song'], params)
    
    def get_album_details(self, album_id: str) -> Optional[Dict]:
        """Get album details."""
        params = {'id': album_id}
        return self._make_request(self.endpoints['album'], params)
    
    def get_artist_details(self, artist_id: str) -> Optional[Dict]:
        """Get artist details."""
        params = {'id': artist_id}
        return self._make_request(self.endpoints['artist'], params)
    
    def get_playlist_details(self, playlist_id: str) -> Optional[Dict]:
        """Get playlist details."""
        params = {'id': playlist_id}
        return self._make_request(self.endpoints['playlist'], params)
    
    def download_file(self, url: str, filepath: str) -> bool:
        """
        Download a file from URL.
        
        Args:
            url: Download URL
            filepath: Local path to save file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Downloading file from {url[:50]}...")
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Log progress for large files
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            if percent % 20 < 1:  # Log every ~20%
                                logger.debug(f"Download progress: {percent:.1f}%")
            
            logger.info(f"Download complete: {filepath} ({downloaded / 1024 / 1024:.2f} MB)")
            return True
            
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False
    
    def get_download_urls(self, song_data: Dict) -> Dict[str, str]:
        """
        Extract download URLs from song data.
        
        Args:
            song_data: Song information from API
            
        Returns:
            Dictionary mapping quality to URL
        """
        urls = {}
        
        # Handle different API response structures
        if 'downloadUrl' in song_data:
            # Your API structure: list of dicts with quality and url
            for item in song_data['downloadUrl']:
                quality = item.get('quality', '')
                url = item.get('url', '')
                if quality and url:
                    # Map to standard quality names
                    if '320' in quality:
                        urls['320kbps'] = url
                    elif '160' in quality:
                        urls['160kbps'] = url
                    elif '128' in quality or '96' in quality:
                        urls['128kbps'] = url
                    elif '48' in quality:
                        urls['48kbps'] = url
                    elif '12' in quality:
                        urls['12kbps'] = url
        
        # Alternative structure: direct media URLs
        elif 'media_url' in song_data:
            urls['default'] = song_data['media_url']
        elif 'media_preview_url' in song_data:
            urls['preview'] = song_data['media_preview_url']
        
        # Sort by quality (highest first)
        quality_order = ['320kbps', '160kbps', '128kbps', '96kbps', '48kbps', '12kbps', 'default', 'preview']
        return {k: urls[k] for k in quality_order if k in urls}
    
    def get_best_image(self, images: List[Dict]) -> str:
        """
        Get the highest quality image URL.
        
        Args:
            images: List of image dictionaries with quality and url
            
        Returns:
            URL of the best quality image
        """
        if not images:
            return ""
        
        # Sort by quality (highest first)
        quality_scores = {
            '500x500': 5,
            '480x480': 4,
            '300x300': 3,
            '150x150': 2,
            '50x50': 1,
            '': 0
        }
        
        sorted_images = sorted(
            images,
            key=lambda x: quality_scores.get(x.get('quality', ''), 0),
            reverse=True
        )
        
        return sorted_images[0].get('url', '') if sorted_images else ""
    
    def extract_primary_artists(self, artists_data: Dict) -> str:
        """
        Extract primary artists names into a string.
        
        Args:
            artists_data: Artists information from API
            
        Returns:
            Comma-separated artist names
        """
        try:
            if 'primary' in artists_data and artists_data['primary']:
                names = []
                for artist in artists_data['primary']:
                    name = artist.get('name', '').strip()
                    if name:
                        names.append(name)
                
                if names:
                    return ', '.join(names[:3])  # Max 3 artists
                    
            # Fallback: check other artist fields
            if 'singers' in artists_data and artists_data['singers']:
                if isinstance(artists_data['singers'], list):
                    return ', '.join([s.get('name', '') for s in artists_data['singers'][:2]])
                else:
                    return str(artists_data['singers'])
                    
            return "Unknown Artist"
            
        except Exception as e:
            logger.warning(f"Failed to extract artists: {e}")
            return "Unknown Artist"
    
    def extract_album_info(self, album_data: Union[Dict, str]) -> Dict:
        """
        Extract album information.
        
        Args:
            album_data: Album data from API
            
        Returns:
            Dictionary with album info
        """
        if isinstance(album_data, dict):
            return {
                'id': album_data.get('id', ''),
                'name': album_data.get('name', 'Unknown Album'),
                'url': album_data.get('url', '')
            }
        else:
            return {
                'name': str(album_data) if album_data else 'Unknown Album',
                'id': '',
                'url': ''
            }
    
    def get_song_metadata(self, song_data: Dict) -> Dict:
        """
        Extract all metadata from song data for MP3 tagging.
        
        Args:
            song_data: Song information from API
            
        Returns:
            Complete metadata dictionary
        """
        # Extract basic info
        title = song_data.get('name', song_data.get('song', 'Unknown Title'))
        
        # Extract artists
        artists_str = self.extract_primary_artists(song_data.get('artists', {}))
        
        # Extract album
        album_info = self.extract_album_info(song_data.get('album', {}))
        
        # Get best image URL
        image_url = self.get_best_image(song_data.get('image', []))
        
        # Compile metadata
        metadata = {
            'id': song_data.get('id', ''),
            'title': title,
            'primary_artists': artists_str,
            'album': album_info['name'],
            'album_id': album_info['id'],
            'year': song_data.get('year', ''),
            'language': song_data.get('language', ''),
            'duration': song_data.get('duration', 0),
            'explicit': song_data.get('explicitContent', False),
            'play_count': song_data.get('playCount', 0),
            'copyright': song_data.get('copyright', ''),
            'label': song_data.get('label', ''),
            'image_url': image_url,
            'has_lyrics': song_data.get('hasLyrics', False),
            'lyrics_id': song_data.get('lyricsId', ''),
            'url': song_data.get('url', '')
        }
        
        return metadata

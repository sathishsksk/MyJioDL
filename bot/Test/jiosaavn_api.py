def extract_song_id_from_url(self, url: str) -> Optional[str]:
    """
    Extract song ID from a JioSaavn URL.
    Returns None if not a valid URL.
    """
    try:
        import re
        
        # Common JioSaavn URL patterns
        patterns = [
            r'/song/[^/]+/([^/?]+)',      # /song/song-name/ID
            r'\?id=([^&]+)',              # ?id=ID
            r'song/([^/]+)/',             # song/ID/
            r'track/([^/]+)/'             # track/ID/
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                song_id = match.group(1)
                logger.info(f"Extracted song ID: {song_id} from URL")
                return song_id
        
        # If no pattern matches, try last part
        url_parts = url.split('/')
        if url_parts:
            last_part = url_parts[-1].split('?')[0]
            if last_part and len(last

import os
import subprocess
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class AudioConverter:
    @staticmethod
    def convert_to_mp3(
        input_path: str,
        output_path: str,
        bitrate: str = "320k",
        metadata: Optional[dict] = None
    ) -> Tuple[bool, str]:
        """
        Convert an audio file to MP3 using FFmpeg.
        
        Args:
            input_path: Path to the source audio file.
            output_path: Path for the output MP3 file.
            bitrate: Target bitrate (e.g., '128k', '320k').
            metadata: Dictionary of metadata to embed (title, artist, etc.).
        
        Returns:
            (success_status, message)
        """
        try:
            # Build the base FFmpeg command
            cmd = [
                'ffmpeg',
                '-i', input_path,      # Input file
                '-b:a', bitrate,       # Audio bitrate
                '-ac', '2',            # Stereo audio
                '-ar', '44100',        # Sample rate
                '-codec:a', 'libmp3lame', # MP3 codec
                '-y'                   # Overwrite output file without asking
            ]
            
            # Add metadata tags if provided
            if metadata:
                meta_mapping = {
                    'title': 'title',
                    'artist': 'artist',
                    'album': 'album',
                    'date': 'date',
                    'genre': 'genre'
                }
                for key, ffmpeg_tag in meta_mapping.items():
                    if key in metadata and metadata[key]:
                        cmd.extend(['-metadata', f'{ffmpeg_tag}={metadata[key]}'])
            
            # Add the output file path
            cmd.append(output_path)
            
            # Run the command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5-minute timeout
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully converted {input_path} to {output_path} at {bitrate}")
                return True, "Conversion successful"
            else:
                logger.error(f"FFmpeg conversion failed: {result.stderr}")
                return False, f"FFmpeg error: {result.stderr[:200]}"
                
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg conversion timed out after 5 minutes.")
            return False, "Conversion timed out."
        except FileNotFoundError:
            logger.error("FFmpeg binary not found. Ensure it is installed in the system PATH.")
            return False, "FFmpeg not found. Check Docker installation."
        except Exception as e:
            logger.error(f"Unexpected error during conversion: {e}")
            return False, f"Unexpected error: {str(e)}"
    
    @staticmethod
    def convert_multiple_qualities(input_path: str, song_id: str) -> dict:
        """
        Convert a single file to both 128kbps and 320kbps MP3.
        Returns a dict with paths for each quality.
        """
        base_name = f"{song_id}"
        qualities = {
            '128kbps': '128k',
            '320kbps': '320k'
        }
        
        results = {}
        for quality_name, bitrate in qualities.items():
            output_path = os.path.join(
                os.path.dirname(input_path),
                f"{base_name}_{quality_name}.mp3"
            )
            
            success, message = AudioConverter.convert_to_mp3(
                input_path, output_path, bitrate
            )
            
            if success:
                results[quality_name] = {
                    'path': output_path,
                    'bitrate': bitrate,
                    'size': os.path.getsize(output_path)
                }
        
        return results

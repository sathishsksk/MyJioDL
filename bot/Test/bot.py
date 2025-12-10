"""
Main Telegram Bot for JioSaavn Music Downloader
Handles commands, searches, and direct JioSaavn URLs.
"""
import os
import re
import logging
import signal
import sys
import tempfile
import asyncio
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

from bot.jiosaavn_api import JioSaavnAPI
from bot.audio_converter import AudioConverter
from bot.utils import (
    download_and_process_image, 
    embed_metadata_to_mp3, 
    sanitize_filename, 
    format_duration,
    ensure_directory
)
from bot.health_server import start_health_server

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize components
jiosaavn = JioSaavnAPI()
converter = AudioConverter()

# User session storage (simple in-memory cache)
user_sessions = {}

def is_jiosaavn_url(text: str) -> bool:
    """Check if text is a JioSaavn URL."""
    patterns = [
        r'jiosaavn\.com/song/',
        r'jiosaavn\.com/track/',
        r'saavn\.com/song/',
        r'jiosaavn\.com/.*\?id=',
        r'saavn\.com/.*\?id='
    ]
    
    text_lower = text.lower()
    return any(pattern in text_lower for pattern in patterns)

def handle_shutdown(signum, frame):
    """Handle graceful shutdown on SIGTERM (Koyeb sends this)"""
    logger.info("Received shutdown signal, exiting...")
    sys.exit(0)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_text = """
🎵 *JioSaavn Music Downloader Bot* 🎵

I can download music from JioSaavn and send it to you as high-quality MP3 files!

*How to use:*
1. Send me a song name (e.g., 'Kesariya')
2. Send a JioSaavn song URL
3. Use /search <song name>
4. Select from results
5. Choose quality (128kbps or 320kbps)
6. Receive song with full metadata!

*Examples:*
- Send: `Kesariya`
- Send: `https://www.jiosaavn.com/song/aasa-kooda/Nz0,YxhYRQI`
- Use: `/search Tum Hi Ho`

*Commands:*
/search <query> - Search for songs
/help - Show help message
/about - About this bot

*Note:* Educational project only.
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = """
*📋 Available Commands:*

*Main Commands:*
/start - Start the bot
/help - Show this help
/search <query> - Search for songs
/about - About this project

*How to Download:*
1. *Search by name:* Send any song name
   Example: `Kesariya` or `Tum Hi Ho`

2. *Send JioSaavn link:* Copy-paste any song URL
   Example: `https://www.jiosaavn.com/song/aasa-kooda/Nz0,YxhYRQI`

*Quality Options:*
• 320kbps - High quality (~7MB for 3-min song)
• 160kbps - Good quality (~3.5MB)
• 128kbps - Fast download (~2MB)

*Features:*
• Search songs from JioSaavn
• Direct URL support
• Multiple quality options
• Full metadata embedding
• Album art included

*College Project by:* @sathishsksk
*API:* github.com/sathishsksk/jiosaavn-api2
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """About command handler"""
    about_text = """
*About This Project*

This Telegram bot is part of a college project demonstrating:
• API integration with JioSaavn
• Telegram Bot development
• Audio processing with FFmpeg
• Docker containerization
• Metadata manipulation

*Technical Stack:*
• Python with python-telegram-bot
• Custom JioSaavn API
• FFmpeg for audio conversion
• Docker for deployment
• Mutagen for metadata

*Developer:* @sathishsksk
*GitHub:* github.com/sathishsksk
*API Repo:* github.com/sathishsksk/jiosaavn-api2

*Educational Use Only*
    """
    await update.message.reply_text(about_text, parse_mode='Markdown')

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command"""
    if not context.args:
        await update.message.reply_text(
            "Please provide a search query.\nExample: `/search Kesariya`",
            parse_mode='Markdown'
        )
        return
    
    query = ' '.join(context.args)
    await update.message.reply_text(f"🔍 Searching: *{query}*", parse_mode='Markdown')
    await perform_search(update, query)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all messages - both song names and URLs"""
    message_text = update.message.text.strip()
    
    if not message_text or message_text.startswith('/'):
        return
    
    # Check if it's a URL
    if is_jiosaavn_url(message_text):
        await handle_jiosaavn_url(update, message_text, context)
    else:
        # Regular song name search
        await update.message.reply_text(f"🔍 Searching: *{message_text}*", parse_mode='Markdown')
        await perform_search(update, message_text)

async def handle_jiosaavn_url(update: Update, url: str, context: ContextTypes.DEFAULT_TYPE):
    """Handle JioSaavn URL directly"""
    message = update.message
    
    # Show processing message
    processing_msg = await message.reply_text(
        "🔗 Processing your JioSaavn link...",
        parse_mode='Markdown'
    )
    
    try:
        # Extract song ID from URL
        song_id = jiosaavn.extract_song_id_from_url(url)
        
        if not song_id:
            await processing_msg.edit_text(
                "❌ Could not extract song information from the URL.\n"
                "Please send a valid JioSaavn song link.\n\n"
                "*Example:*\n"
                "`https://www.jiosaavn.com/song/song-name/ID`"
            )
            return
        
        # Get song details
        song_data = jiosaavn.get_song_details(song_id)
        
        if not song_data or 'results' not in song_data or not song_data['results']:
            await processing_msg.edit_text(
                "❌ Could not fetch song details from the API.\n"
                "The link might be invalid or the song might not be available."
            )
            return
        
        song = song_data['results'][0]
        
        # Show song info
        title = song.get('name', 'Unknown Title')
        artists = jiosaavn.extract_primary_artists(song.get('artists', {}))
        
        await processing_msg.edit_text(
            f"✅ *Found song from link!*\n\n"
            f"🎵 *{title}*\n"
            f"👤 *Artist:* {artists}\n\n"
            f"*Select download quality:*",
            parse_mode='Markdown'
        )
        
        # Create quality selection buttons
        await show_song_options(processing_msg, song_id, song, is_from_url=True)
        
    except Exception as e:
        logger.error(f"URL handling error: {e}")
        await processing_msg.edit_text(
            "❌ Error processing the link. Please try again with a different URL."
        )

async def perform_search(update, query):
    """Perform search and display results"""
    user_id = update.effective_user.id
    
    # Search using your API
    results = jiosaavn.search_songs(query)
    
    if not results or 'results' not in results or not results['results']:
        await update.message.reply_text("❌ No results found. Try a different search term.")
        return
    
    # Store results in user session
    user_sessions[user_id] = {
        'results': results['results'],
        'query': query,
        'timestamp': asyncio.get_event_loop().time()
    }
    
    # Create inline keyboard with results (max 10)
    keyboard = []
    for i, song in enumerate(results['results'][:10], 1):
        title = song.get('name', 'Unknown')[:35]
        artists = jiosaavn.extract_primary_artists(song.get('artists', {}))
        
        # Format button text
        button_text = f"{i}. {title}"
        if artists and artists != "Unknown Artist":
            artist_display = artists[:20] + "..." if len(artists) > 20 else artists
            button_text += f"\n   👤 {artist_display}"
        
        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"select_{song['id']}"
            )
        ])
    
    # Add cancel button
    keyboard.append([
        InlineKeyboardButton("❌ Cancel", callback_data="cancel")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send results
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"📋 *Found {len(results['results'])} results for '{query}':*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"📋 *Found {len(results['results'])} results for '{query}':*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def show_song_options(query, song_id, song=None, is_from_url=False):
    """Show download options for selected song"""
    if not song:
        # Get song details if not provided
        song_data = jiosaavn.get_song_details(song_id)
        if not song_data or 'results' not in song_data:
            await query.edit_message_text("❌ Could not fetch song details.")
            return
        song = song_data['results'][0]
    
    # Extract information
    title = song.get('name', 'Unknown Title')
    artists = jiosaavn.extract_primary_artists(song.get('artists', {}))
    album = song.get('album', {}).get('name', 'Unknown Album')
    duration = format_duration(song.get('duration', 0))
    year = song.get('year', '')
    
    # Create info message
    info_text = f"""
🎵 *{title}*
👤 *Artist:* {artists}
💿 *Album:* {album}
⏱ *Duration:* {duration}
    """
    if year:
        info_text += f"📅 *Year:* {year}\n"
    
    # Check available download qualities
    download_urls = jiosaavn.get_download_urls(song)
    
    # Create download buttons (highest quality first)
    keyboard = []
    
    if '320kbps' in download_urls:
        keyboard.append([
            InlineKeyboardButton(
                "🎵 HIGH Quality (320kbps) - ~7MB",
                callback_data=f"download_{song_id}_320"
            )
        ])
    
    if '160kbps' in download_urls:
        keyboard.append([
            InlineKeyboardButton(
                "👍 GOOD Quality (160kbps) - ~3.5MB",
                callback_data=f"download_{song_id}_160"
            )
        ])
    
    if '128kbps' in download_urls:
        keyboard.append([
            InlineKeyboardButton(
                "⚡ FAST Download (128kbps) - ~2MB",
                callback_data=f"download_{song_id}_128"
            )
        ])
    
    # Fallback if no specific quality found
    if not keyboard and download_urls:
        for quality, url in list(download_urls.items())[:3]:  # Show first 3
            keyboard.append([
                InlineKeyboardButton(
                    f"⬇️ Download {quality}",
                    callback_data=f"download_{song_id}_{quality.replace('kbps', '')}"
                )
            ])
    
    # Add action buttons
    action_row = []
    if not is_from_url:
        action_row.append(InlineKeyboardButton("🔍 Search Again", callback_data="search_again"))
    action_row.append(InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    keyboard.append(action_row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Try to send with thumbnail
    image_url = jiosaavn.get_best_image(song.get('image', []))
    if image_url and hasattr(query, 'message'):
        try:
            await query.message.reply_photo(
                photo=image_url,
                caption=info_text + "\n*Select download quality:*",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            await query.delete_message()
            return
        except Exception as e:
            logger.warning(f"Could not send photo: {e}")
    
    # Fallback to text only
    await query.edit_message_text(
        info_text + "\n*Select download quality:*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("select_"):
        song_id = data.split("_")[1]
        await show_song_options(query, song_id)
    
    elif data.startswith("download_"):
        # Format: download_{song_id}_{quality}
        parts = data.split("_")
        if len(parts) == 3:
            song_id = parts[1]
            quality = parts[2]
            await process_download(query, song_id, quality)
    
    elif data == "search_again":
        await query.edit_message_text("Send me a song name or JioSaavn URL to search:")
    
    elif data == "cancel":
        await query.edit_message_text("Operation cancelled.")

async def process_download(query, song_id, quality):
    """Complete download, conversion, and send process"""
    await query.edit_message_text(f"⏬ Starting download ({quality}kbps)...")
    
    try:
        # 1. Get song details
        song_data = jiosaavn.get_song_details(song_id)
        if not song_data or 'results' not in song_data:
            await query.edit_message_text("❌ Failed to get song details.")
            return
        
        song = song_data['results'][0]
        
        # 2. Get download URL for selected quality
        download_urls = jiosaavn.get_download_urls(song)
        
        # Map user quality to actual quality in API
        quality_map = {
            '320': '320kbps',
            '160': '160kbps',
            '128': '128kbps' if '128kbps' in download_urls else '96kbps'
        }
        
        actual_quality = quality_map.get(quality)
        if not actual_quality or actual_quality not in download_urls:
            # Try any available quality
            if download_urls:
                actual_quality = list(download_urls.keys())[0]
            else:
                await query.edit_message_text(f"❌ {quality}kbps download not available.")
                return
        
        download_url = download_urls[actual_quality]
        
        # 3. Download original file
        await query.edit_message_text("📥 Downloading audio...")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.m4a') as tmp_file:
            temp_input = tmp_file.name
        
        if not jiosaavn.download_file(download_url, temp_input):
            await query.edit_message_text("❌ Download failed.")
            if os.path.exists(temp_input):
                os.unlink(temp_input)
            return
        
        # 4. Convert to MP3
        await query.edit_message_text("🔄 Converting to MP3...")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_mp3:
            temp_output = tmp_mp3.name
        
        # Set bitrate for conversion
        bitrate_map = {
            '320': '320k',
            '160': '160k',
            '128': '128k',
            '96': '128k'  # Map 96kbps to 128k
        }
        
        bitrate = bitrate_map.get(quality, '160k')
        
        # Convert using FFmpeg
        success, message = converter.convert_to_mp3(
            temp_input,
            temp_output,
            bitrate=bitrate,
            metadata=None  # We'll add metadata separately
        )
        
        if not success:
            await query.edit_message_text(f"❌ Conversion failed: {message}")
            for file_path in [temp_input, temp_output]:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            return
        
        # 5. Prepare metadata
        await query.edit_message_text("🏷️ Adding metadata and album art...")
        
        metadata = {
            'title': song.get('name', 'Unknown'),
            'primary_artists': jiosaavn.extract_primary_artists(song.get('artists', {})),
            'album': song.get('album', {}).get('name', 'Unknown Album'),
            'year': song.get('year', ''),
            'language': song.get('language', ''),
            'id': song.get('id', '')
        }
        
        # Download and process album art
        cover_art_bytes = None
        image_url = jiosaavn.get_best_image(song.get('image', []))
        if image_url:
            cover_art_bytes = download_and_process_image(image_url, song_id)
        
        # Embed metadata into MP3
        embed_success, embed_message = embed_metadata_to_mp3(temp_output, metadata, cover_art_bytes)
        if not embed_success:
            logger.warning(f"Metadata embedding failed: {embed_message}")
        
        # 6. Send to user
        await query.edit_message_text("📤 Uploading to Telegram...")
        
        # Prepare caption
        title = song.get('name', 'Unknown')
        artists = metadata['primary_artists']
        album = metadata['album']
        
        caption = f"🎵 *{title}*\n👤 {artists}\n💿 {album}"
        if metadata['year']:
            caption += f"\n📅 {metadata['year']}"
        caption += f"\n📊 {quality}kbps"
        
        # Send audio file
        try:
            with open(temp_output, 'rb') as audio_file:
                await query.message.reply_audio(
                    audio=InputFile(
                        audio_file, 
                        filename=f"{sanitize_filename(title)}.mp3"
                    ),
                    caption=caption,
                    parse_mode='Markdown',
                    duration=int(song.get('duration', 0)),
                    title=title[:64],
                    performer=artists[:64]
                )
            
            await query.edit_message_text("✅ Download complete! Check your chat for the song.")
            
        except Exception as e:
            logger.error(f"Failed to send audio: {e}")
            await query.edit_message_text(f"❌ Failed to send: {str(e)[:100]}")
        
    except Exception as e:
        logger.error(f"Download process error: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)[:100]}")
    
    finally:
        # 7. Cleanup temporary files
        for file_path in [temp_input, temp_output]:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except Exception as e:
                logger.warning(f"Could not delete temp file {file_path}: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors gracefully"""
    logger.error(f"Update {update} caused error {context.error}")
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ An error occurred. Please try again."
            )
        elif update.message:
            await update.message.reply_text(
                "❌ An error occurred. Please try again."
            )
    except:
        pass  # Silently ignore if we can't send error message

def main():
    """Start the bot"""
    # Setup signal handler for graceful shutdown
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    # Get bot token from environment
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        logger.error("BOT_TOKEN not set in environment variables")
        sys.exit(1)
    
    # Start health check server (required for Koyeb)
    health_port = int(os.environ.get("PORT", "8080"))
    start_health_server(health_port)
    logger.info(f"Health check endpoint available at :{health_port}/health")
    
    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("about", about_command))
    
    # Add message handler for all text (song names and URLs)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_message
    ))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Check FFmpeg installation
    logger.info("Checking FFmpeg installation...")
    try:
        import subprocess
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("FFmpeg is available")
        else:
            logger.warning("FFmpeg check failed")
    except FileNotFoundError:
        logger.error("FFmpeg not found! Audio conversion will not work.")
    
    # Ensure download directory exists
    download_folder = os.environ.get("DOWNLOAD_FOLDER", "downloads")
    ensure_directory(download_folder)
    
    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        close_loop=False
    )

if __name__ == '__main__':
    main()

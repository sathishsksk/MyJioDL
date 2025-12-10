import os
import logging
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from bot.jiosaavn_api import JioSaavnAPI
from bot.audio_converter import AudioConverter
from bot.utils import download_and_process_image, embed_metadata_to_mp3, sanitize_filename, format_duration
import asyncio

# Setup logging
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_text = """
🎵 *JioSaavn Music Downloader Bot* 🎵

I can download music from JioSaavn and send it to you as high-quality MP3 files with metadata and album art!

*How to use:*
1. Send me a song name (e.g., 'Kesariya')
2. Or use /search <song name>
3. Select from the search results
4. Choose your preferred quality (128kbps or 320kbps)
5. Receive the song with full metadata!

*Commands:*
/search <query> - Search for songs
/help - Show this help message
/about - About this bot

*Note:* This bot is for educational purposes as part of a college project.
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = """
*Available Commands:*

*Main Commands:*
/start - Start the bot
/help - Show this help
/search <query> - Search for songs
/about - About this project

*Direct Usage:*
Simply send a song name to search and download!

*Features:*
• Search songs from JioSaavn
• Download with 128kbps or 320kbps quality
• Full metadata embedding (artist, album, year)
• Album art included
• Clean, organized interface

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
    await perform_search(update, query)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle direct song name messages"""
    query = update.message.text.strip()
    if not query or query.startswith('/'):
        return
    
    await update.message.reply_text(f"🔍 Searching: *{query}*", parse_mode='Markdown')
    await perform_search(update, query)

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
        artists = ', '.join([artist.get('name', '') 
                           for artist in song.get('artists', {}).get('primary', [])[:2]])
        
        # Format button text
        button_text = f"{i}. {title}"
        if artists:
            button_text += f" - {artists}" if len(artists) < 20 else f" - {artists[:17]}..."
        
        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"select_{song['id']}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"📋 *Found {len(results['results'])} results for '{query}':*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
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
    
    elif data == "cancel":
        await query.edit_message_text("Operation cancelled.")
        if user_id in user_sessions:
            del user_sessions[user_id]

async def show_song_options(query, song_id):
    """Show download options for selected song"""
    await query.edit_message_text("📥 Fetching song details...")
    
    # Get song details from your API
    song_data = jiosaavn.get_song_details(song_id)
    
    if not song_data or 'results' not in song_data or not song_data['results']:
        await query.edit_message_text("❌ Could not fetch song details.")
        return
    
    song = song_data['results'][0]
    
    # Extract information
    title = song.get('name', 'Unknown Title')
    artists = ', '.join([artist.get('name', '') 
                        for artist in song.get('artists', {}).get('primary', [])])
    album = song.get('album', {}).get('name', 'Unknown Album')
    duration = format_duration(song.get('duration', 0))
    year = song.get('year', '')
    
    # Create info message
    info_text = f"""
🎵 *{title}*
👤 *Artist:* {artists or 'Unknown'}
💿 *Album:* {album}
⏱ *Duration:* {duration}
    """
    if year:
        info_text += f"📅 *Year:* {year}\n"
    
    # Check available download qualities
    download_urls = jiosaavn.get_download_urls(song)
    available_qualities = []
    
    if '320kbps' in download_urls:
        available_qualities.append('320kbps')
    if '160kbps' in download_urls:
        available_qualities.append('160kbps')
    if '128kbps' in download_urls or '96kbps' in download_urls:
        # Map 96kbps to 128kbps for user display
        available_qualities.append('128kbps')
    
    # Create download buttons
    keyboard = []
    for quality in available_qualities:
        keyboard.append([
            InlineKeyboardButton(
                f"⬇️ Download {quality} MP3",
                callback_data=f"download_{song_id}_{quality}"
            )
        ])
    
    # Add action buttons
    keyboard.append([
        InlineKeyboardButton("🔍 Search Again", callback_data="search_again"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Try to send with thumbnail
    image_url = jiosaavn.get_best_image(song.get('image', []))
    if image_url:
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

async def process_download(query, song_id, quality):
    """Complete download, conversion, and send process"""
    await query.edit_message_text(f"⏬ Starting download ({quality})...")
    
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
        '320kbps': '320kbps',
        '128kbps': '128kbps' if '128kbps' in download_urls else '96kbps'
    }
    
    actual_quality = quality_map.get(quality)
    if not actual_quality or actual_quality not in download_urls:
        await query.edit_message_text(f"❌ {quality} download not available.")
        return
    
    download_url = download_urls[actual_quality]
    
    # 3. Download original file
    await query.edit_message_text("📥 Downloading audio...")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.m4a') as tmp_file:
        temp_input = tmp_file.name
    
    if not jiosaavn.download_file(download_url, temp_input):
        await query.edit_message_text("❌ Download failed.")
        return
    
    # 4. Convert to MP3
    await query.edit_message_text("🔄 Converting to MP3...")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_mp3:
        temp_output = tmp_mp3.name
    
    # Set bitrate for conversion
    bitrate = '320k' if '320' in quality else '128k'
    
    success, message = converter.convert_to_mp3(
        temp_input,
        temp_output,
        bitrate=bitrate,
        metadata=None  # We'll add metadata separately
    )
    
    if not success:
        await query.edit_message_text(f"❌ Conversion failed: {message}")
        os.unlink(temp_input)
        return
    
    # 5. Download and embed metadata
    await query.edit_message_text("🏷️ Adding metadata and album art...")
    
    # Prepare metadata
    metadata = {
        'title': song.get('name', 'Unknown'),
        'primary_artists': song.get('artists', {}).get('primary', []),
        'album': song.get('album', {}),
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
    if not embed_metadata_to_mp3(temp_output, metadata, cover_art_bytes):
        logger.warning("Metadata embedding failed, but continuing...")
    
    # 6. Send to user
    await query.edit_message_text("📤 Uploading to Telegram...")
    
    try:
        # Prepare caption
        title = song.get('name', 'Unknown')
        artists = ', '.join([artist.get('name', '') 
                           for artist in song.get('artists', {}).get('primary', [])])
        album = song.get('album', {}).get('name', 'Unknown Album')
        
        caption = f"🎵 *{title}*\n👤 {artists}\n💿 {album}"
        if song.get('year'):
            caption += f"\n📅 {song['year']}"
        caption += f"\n📊 {quality}"
        
        # Send audio file
        with open(temp_output, 'rb') as audio_file:
            await query.message.reply_audio(
                audio=InputFile(audio_file, filename=f"{sanitize_filename(title)}.mp3"),
                caption=caption,
                parse_mode='Markdown',
                duration=int(song.get('duration', 0)),
                title=title[:64],  # Telegram has limits
                performer=artists[:64]
            )
        
        await query.edit_message_text("✅ Download complete! Check your chat for the song.")
        
    except Exception as e:
        logger.error(f"Failed to send audio: {e}")
        await query.edit_message_text(f"❌ Failed to send: {str(e)[:100]}")
    
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
    # Get bot token from environment
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        logger.error("BOT_TOKEN not set in environment variables")
        return
    
    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("about", about_command))
    
    # Add message handler for direct song names
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
    
    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

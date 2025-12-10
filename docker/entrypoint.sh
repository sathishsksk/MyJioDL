#!/bin/bash
set -e

echo "Starting JioSaavn Telegram Bot..."

# You can run database migrations or other setup here if needed in the future
# Example: python manage.py migrate

# Start the main bot application
exec python -m bot.bot

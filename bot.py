import os
import re
import requests
from urllib.parse import urlparse, parse_qs
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from pymongo import MongoClient, errors
from threading import Thread
import logging
from terabox import extract_download_url, is_valid_terabox_link
from tools import get_formatted_size

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
COOKIE = os.getenv("TERABOX_COOKIE")

# Initialize MongoDB client
try:
    client = MongoClient(MONGODB_URI)
    db = client.get_database("terabox_bot_db")
    users_collection = db.get_collection("users")
except errors.ConnectionFailure as e:
    logger.error(f"Could not connect to MongoDB: {e}")

def start(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    try:
        if not users_collection.find_one({"user_id": user.id}):
            users_collection.insert_one({
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name
            })
        update.message.reply_text('Hi! Send me a TeraBox link and I will download it for you.')
    except Exception as e:
        logger.error(f"Error in start handler: {e}")
        update.message.reply_text('An error occurred while processing your request.')

def download_file(url: str, filename: str) -> None:
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise

def handle_terabox_link(update: Update, context: CallbackContext) -> None:
    url = update.message.text.strip()
    if not is_valid_terabox_link(url):
        update.message.reply_text("Invalid TeraBox link. Please provide a valid TeraBox link.")
        return

    try:
        file_info = extract_download_url(url)
        if not file_info:
            update.message.reply_text("Failed to extract download information from the provided link.")
            return

        thumbnail_url = file_info.get("thumbnail_url")
        size = file_info.get("size")
        direct_link = file_info.get("direct_link")

        update.message.reply_text(f"Downloading: {file_info['file_name']}\nSize: {size}")
        
        # Start downloading the file in a separate thread
        Thread(target=download_file, args=(direct_link, f"{file_info['file_name']}")).start()

        # Send the thumbnail
        if thumbnail_url:
            update.message.reply_photo(photo=thumbnail_url)

        update.message.reply_text("Download started successfully.")
    except Exception as e:
        logger.error(f"Error handling TeraBox link: {e}")
        update.message.reply_text("An error occurred while processing your request.")

def main() -> None:
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    # Register handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_terabox_link))

    # Start the Bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()

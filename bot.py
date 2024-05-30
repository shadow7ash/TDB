import os
import requests
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from pymongo import MongoClient, errors
from threading import Thread
import logging

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

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

def download_file(update: Update, context: CallbackContext) -> None:
    url = update.message.text
    update.message.reply_text('Starting download...')
    thread = Thread(target=download_and_send_file, args=(update, context, url))
    thread.start()

def download_and_send_file(update: Update, context: CallbackContext, url: str) -> None:
    try:
        response = requests.get(url, stream=True)
        file_name = url.split("/")[-1]

        if response.status_code == 200:
            with open(file_name, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
            update.message.reply_text(f'File {file_name} downloaded successfully. Uploading...')
            with open(file_name, 'rb') as file:
                context.bot.send_document(chat_id=update.message.chat_id, document=file)
            os.remove(file_name)
        else:
            update.message.reply_text('Failed to download the file.')
    except Exception as e:
        logger.error(f"Error in download_and_send_file: {e}")
        update.message.reply_text('An error occurred while downloading the file.')

def main():
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, download_file))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()

import os
import requests
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from pymongo import MongoClient, errors
from threading import Thread
import logging
from bs4 import BeautifulSoup
import re

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")

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

def is_valid_terabox_link(url: str) -> bool:
    parsed_url = urlparse(url)
    return "terabox" in parsed_url.netloc

def extract_download_url(terabox_url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"}
    response = requests.get(terabox_url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to access TeraBox link: {response.status_code}")

    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Hypothetical pattern to find the download link, you need to adjust this based on the actual HTML structure
    script_tag = soup.find('script', text=re.compile('var downloadUrl'))
    if not script_tag:
        raise Exception("Could not find the download URL in the page source")
    
    download_url_match = re.search(r'var downloadUrl = "(.*?)";', script_tag.string)
    if not download_url_match:
        raise Exception("Could not extract the download URL from the script tag")
    
    download_url = download_url_match.group(1)
    return download_url

def get_file_name_from_response(response):
    content_disposition = response.headers.get('content-disposition')
    if content_disposition:
        fname = content_disposition.split('filename=')[1].strip('"')
    else:
        fname = urlparse(response.url).path.split('/')[-1]
    return fname

def download_file(update: Update, context: CallbackContext) -> None:
    url = update.message.text
    if is_valid_terabox_link(url):
        update.message.reply_text('Starting download...')
        thread = Thread(target=download_and_send_file, args=(update, context, url))
        thread.start()
    else:
        update.message.reply_text('Please provide a valid TeraBox link.')

def download_and_send_file(update: Update, context: CallbackContext, url: str) -> None:
    try:
        download_url = extract_download_url(url)
        response = requests.get(download_url, stream=True)
        if response.status_code == 200:
            file_name = get_file_name_from_response(response)
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

import os
import re
import requests
from urllib.parse import urlparse, parse_qs
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from pymongo import MongoClient, errors
from threading import Thread
import logging

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
COOKIE_FILE_PATH = os.getenv("COOKIE_FILE_PATH")  # path to the cookie file

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
    patterns = [
        r"ww\.mirrobox\.com",
        r"www\.nephobox\.com",
        r"freeterabox\.com",
        r"www\.freeterabox\.com",
        r"1024tera\.com",
        r"4funbox\.co",
        r"www\.4funbox\.com",
        r"mirrobox\.com",
        r"nephobox\.com",
        r"terabox\.app",
        r"terabox\.com",
        r"www\.terabox\.ap",
        r"www\.terabox\.com",
        r"www\.1024tera\.co",
        r"www\.momerybox\.com",
        r"teraboxapp\.com",
        r"momerybox\.com",
        r"tibibox\.com",
        r"www\.tibibox\.com",
        r"www\.teraboxapp\.com",
    ]
    for pattern in patterns:
        if re.search(pattern, url):
            return True
    return False

def find_between(data: str, first: str, last: str) -> str:
    try:
        start = data.index(first) + len(first)
        end = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None

def extract_surl_from_url(url: str) -> str:
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    surl = query_params.get("surl", [])
    return surl[0] if surl else None

def parse_cookie_file(cookie_file: str) -> dict:
    cookies = {}
    with open(cookie_file, 'r') as fp:
        for line in fp:
            if not line.startswith('#'):
                line_fields = line.strip().split('\t')
                if len(line_fields) >= 7:
                    cookie_name = line_fields[5]
                    cookie_value = line_fields[6]
                    cookies[cookie_name] = cookie_value
    return cookies

def extract_download_url(terabox_url: str) -> dict:
    session = requests.Session()
    cookies = parse_cookie_file(COOKIE_FILE_PATH)
    session.cookies.update(cookies)

    response = session.get(terabox_url)
    domain, surl = extract_domain_and_surl(response.url)

    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': f'https://{domain}/sharing/link?surl={surl}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36'
    }

    api_url = f'https://www.terabox.com/share/list?app_id=250528&shorturl={surl}&root=1'
    response = session.get(api_url, headers=headers)

    try:
        result = response.json()['list'][0]['dlink']
    except KeyError:
        logger.error("Failed to get download link")
        raise Exception("Failed to get download link")

    return result

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
            file_name = url.split('/')[-1] + '.zip'
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
        update.message.reply_text(f'An error occurred while downloading the file: {e}')

def main():
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, download_file))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()

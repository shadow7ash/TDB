import os
import re
import requests
from urllib.parse import urlparse, parse_qs
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from pymongo import MongoClient, errors
from threading import Thread
import logging
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

def extract_download_url(terabox_url: str) -> dict:
    session = requests.Session()
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        "Connection": "keep-alive",
        "Cookie": COOKIE,
        "DNT": "1",
        "Host": "www.terabox.app",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

    response = session.get(terabox_url, headers=headers)
    response = session.get(response.url, headers=headers)
    logid = find_between(response.text, "dp-logid=", "&")
    jsToken = find_between(response.text, "fn%28%22", "%22%29")
    bdstoken = find_between(response.text, 'bdstoken":"', '"')
    shorturl = extract_surl_from_url(response.url)

    if not shorturl:
        logger.error("Short URL extraction failed")
        raise Exception("Short URL extraction failed")

    reqUrl = f"https://www.terabox.app/share/list?app_id=250528&web=1&channel=0&jsToken={jsToken}&dp-logid={logid}&page=1&num=20&by=name&order=asc&site_referer=&shorturl={shorturl}&root=1"
    response = session.get(reqUrl, headers=headers)

    if response.status_code != 200:
        logger.error("Failed to get share list")
        raise Exception("Failed to get share list")

    data = response.json()
    logger.debug(f"Response JSON: {data}")

    if data["errno"] != 0 or not data.get("list"):
        logger.error("Error in response data or no list found")
        raise Exception("Error in response data or no list found")

    file_info = data["list"][0]
    logger.debug(f"File Info: {file_info}")

    response = session.head(file_info["dlink"], headers=headers)
    direct_link = response.headers.get("location")

    if not direct_link:
        logger.error("Direct link extraction failed")
        raise Exception("Direct link extraction failed")

    file_data = {
        "file_name": file_info["server_filename"],
        "download_url": file_info["dlink"],
        "direct_link": direct_link,
        "thumbnail_url": file_info["thumbs"]["url3"],
        "size": get_formatted_size(int(file_info["size"])),
        "size_bytes": int(file_info["size"])
    }

    return file_data

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

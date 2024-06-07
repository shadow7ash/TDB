import os
import re
import requests
from urllib.parse import urlparse, parse_qs
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from threading import Thread
import logging
from pymongo import MongoClient

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
COOKIE = os.getenv("TERABOX_COOKIE")
MONGODB_URI = os.getenv("MONGODB_URI")

# Connect to MongoDB
client = MongoClient(MONGODB_URI)
db = client.get_default_database()
users_collection = db.users

def start(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    user_data = {
        "_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }
    users_collection.insert_one(user_data)
    update.message.reply_text('Hi! Send me a TeraBox link and I will download it for you.')

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
    logger.debug(f"Direct Link: {direct_link}")

    return {
        "file_name": file_info["server_filename"],
        "direct_link": direct_link
    }

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
        file_info = extract_download_url(url)
        response = requests.get(file_info["direct_link"], stream=True)
        file_size = int(response.headers.get('Content-Length', 0))
        file_name = file_info["file_name"]

        with open(file_name, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        update.message.reply_document(document=open(file_name, 'rb'), filename=file_name)
        os.remove(file_name)
    except Exception as e:
        logger.error(f"Error in download_and_send_file: {e}")
        update.message.reply_text('An error occurred while processing your request.')

def main() -> None:
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
   

import re
from urllib.parse import urlparse, parse_qs
import requests
from config import COOKIE
from tools import get_formatted_size

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
        raise Exception("Short URL extraction failed")

    reqUrl = f"https://www.terabox.app/share/list?app_id=250528&web=1&channel=0&jsToken={jsToken}&dp-logid={logid}&page=1&num=20&by=name&order=asc&site_referer=&shorturl={shorturl}&root=1"
    response = session.get(reqUrl, headers=headers)

    if response.status_code != 200:
        raise Exception("Failed to get share list")

    data = response.json()

    if data["errno"] != 0 or not data.get("list"):
        raise Exception("Error in response data or no list found")

    file_info = data["list"][0]

    response = session.head(file_info["dlink"], headers=headers)
    direct_link = response.headers.get("location")

    if not direct_link:
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

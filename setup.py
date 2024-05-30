from setuptools import setup, find_packages

setup(
    name='terabox_downloader_bot',
    version='1.0',
    packages=find_packages(),
    install_requires=[
        'python-telegram-bot==13.7',
        'requests==2.25.1',
        'pymongo[srv]==3.11.4'
        'dnspython==2.1.0'
        'beautifulsoup4'
    ],
)

from setuptools import setup, find_packages

setup(
    name='terabox_downloader_bot',
    version='1.0',
    packages=find_packages(),
    install_requires=[
        'python-telegram-bot==13.7',
        'requests',
        'pymongo[srv]'
        'dnspython'
        'beautifulsoup4'
    ],
)

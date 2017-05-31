from distutils.core import setup

setup(
        name = 'web_delta',
        packages = ['web_delta'],
        version = '0.1.2',
        description = 'A batch web scraping library designed for use with frequently updating sites',
        author = 'Nolan Buchanan',
        author_email = 'ncbuchan@gmail.com',
        url = 'https://github.com/N-Buchanan/web_delta', #github
        download_url = 'https://github.com/N-Buchanan/web_delta/archive/0.1.2.tar.gz',
        keywords = ['web', 'scraping', 'delta', 'changes'],
        install_requires=[
            'aiohttp==2.1.0',
            'Flask==0.12.2'
        ],
        classifiers = []
        )

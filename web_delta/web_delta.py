import asyncio
import aiohttp
import pickle
import os
import time
import threading
from collections import namedtuple


class RateLimit:
    """
        Class to provide rate limits to force specific wait times between network calls
    """
    def __init__(self, seconds, minutes, hours, days):
        self.seconds = seconds
        self.minutes = minutes
        self.hours = hours
        self.days = days

Task = namedtuple('Task', ['url', 'func'])

class WebDelta:
    """
        Simple async library to check multiple websites for changes

        rate_limit -- RateLimit object. Only used for the time to pause between executions
                      when get_continuous_all or get_continuous_new is called. (default 10 minutes)
        retry_limit -- The number of times to retry a request if the registered function returns None.
                       (default 5)
        wait_between_retries -- Whether or not to wait between retries when the registered
                                function returns None. (default True)
        cache_file -- String. The name of the file to store the cache in. (default None)
    """
    def __init__(self, rate_limit=None, retry_limit=5, wait_between_retries=True, cache_file=None):
        self.tasks = []
        self.retry_limit = retry_limit
        self.wait_between_retries = wait_between_retries
        self.cache_file = cache_file

        if rate_limit is None: # default to once a minute
            self.rate_limit = 60 # seconds
        else:
            self.rate_limit = rate_limit.seconds + (60 * rate_limit.minutes) + (3600 * rate_limit.hours) + (3600 * 24 * rate_limit.days)

        self.cache = {}
        self.read_cache_file()


    def read_cache_file(self):
        """
            Reads the cache file if it exists to compare against most recent
        """
        if self.cache_file is not None:
            try:
                with open(self.cache_file, 'rb') as handle:
                    self.cache = pickle.load(handle)
            except FileNotFoundError:
                # file might not exist if we haven't run this before
                pass


    def update_cache_file(self):
        if self.cache_file is not None:
            with open(self.cache_file, 'wb') as handle:
                pickle.dump(self.cache, handle, protocol=pickle.HIGHEST_PROTOCOL)


    def register(self, url, func):
        """
            Register a new web scraping task.

            url should be the url you want to scrape.
            func should be the function that will extract the information you care about
            from the html to be found at url.
        """
        # task = asyncio.ensure_future(self._execute(url, func))
        task = Task(url, func)
        self.tasks.append(task)


    def clear_tasks(self):
        """
            Remove all registered tasks, clear the cache,  and delete the cache file
        """
        self.tasks.clear()
        try:
            os.remove(self.cache_file)
        except FileNotFoundError:
            # We wanted it gone anyway
            pass
        self.cache = {}


    def get_new(self, loop=None):
        """
            Release all the registered tasks to begin scraping.
            Returns only the results that are different from the cached versions.
            If the cache doesn't contain anything for a particular scraping task,
            (it has been newly registered or every previous attempt has returned None)
            that scraping task will be returned.

            Results are returned as a list of (url, result) tuples where the result is
            return value of calling the registered function on the html from url.
        """
        if loop is None:
            loop = asyncio.get_event_loop()
        else:
            asyncio.set_event_loop(loop)

        futures = []
        for task in self.tasks:
            futures.append(asyncio.ensure_future(self._execute(task.url, task.func)))
        # result = loop.run_until_complete(asyncio.gather(*self.tasks))
        result = loop.run_until_complete(asyncio.gather(*futures))

        # remove Nones from list (the sites that haven't changed)
        result = list(filter((lambda x : x[1] is not None), result))

        self.update_cache_file()
        # print('result {}'.format(result))
        return result


    def get_all(self):
        """
            Return every result from running all of the registered scraping tasks
            whether the result is new or not.

            Results are returned as a list of (url, result) tuples where the result is
            return value of calling the registered function on the html from url.
        """

        # We want the most up-to-date results but don't want to be forced to call execute
        # before calling get_all
        self.get_new()
        return [(k[0], v) for k,v in self.cache.items()]


    def get_continuous_new(self, queue):
        """
            Appends all new results to the provided queue. Spawns a new thread and executes
            calls continuously until stop is called. Only appends new results.
        """

        loop = asyncio.get_event_loop()
        thread = threading.Thread(target=self._get_continuous, args=[queue], kwargs={'get_all': False, 'loop': loop})
        thread.start()

    def get_continuous_all(self, queue):
        """
            Appends all new results to the provided queue. Spawns a new thread and executes
            calls continuously until stop is called. Appends cache contents first.
        """

        loop = asyncio.get_event_loop()
        thread = threading.Thread(target=self._get_continuous, args=[queue], kwargs={'get_all': True, 'loop': loop})
        thread.start()


    def _get_continuous(self, queue, get_all=False, loop=None):
        """
            Internal function that appends results to the provided queue. If get_all is True
            then the results already in the cache will be appended to the queue once.
        """

        # mechanism to allow clients to stop execution
        self.loop = True

        if get_all:
            # only include "old" results if asked for them
            for key, result in self.cache.items():
                queue.put((key[0], result))

            # this is run in a separate thread so we don't care about blocking
            time.sleep(self.rate_limit)


        while(self.loop):
            results = self.get_new(loop=loop)

            for result in results:
                # print('putting {}'.format(result))
                queue.put(result)
            
            # this is run in a separate thread so we don't care about blocking
            time.sleep(self.rate_limit)


    def stop(self):
        """
            Signals _get_continuous to stop execution
        """
        self.loop = False

    async def _fetch(self, url, session):
        """
            Internal helper function to get the html from a url.
        """
        async with session.get(url) as response:
            return await response.text()


    async def _execute(self, url, func):
        """
            Get the html from the specified url, run func on it to extract a specific part,
            and compare it against a cached version.

            If a response comes back empty, this function will try to get a proper response
            up to retry_limit times, waiting a second longer between requests as more are issued.

        """
        # print('executing')
        async with aiohttp.ClientSession() as session:
            html = await self._fetch(url, session)

        cached_version = self.cache.get((url, func.__name__))
        live_version = func(html)

        # if live_version is None, assume that there was a bad request, retry up to retry times
        # possibly waiting slightly longer each time
        retries = self.retry_limit
        while live_version is None and retries > 0:
            if self.wait_between_retries:
                await asyncio.sleep(self.retry_limit - retries) # wait one second longer on each retry
            async with aiohttp.ClientSession() as session:
                html = await self._fetch(url, session)
            live_version = func(html)
            retries -= 1

        # print('live_version {}'.format(live_version))
        if live_version != cached_version and live_version is not None:
            # update cached version
            self.cache[(url, func.__name__)] = live_version
            # print('updated cache')
            # print(self.cache)

            return (url, live_version)

        # return None in place of live_version to signify that there has been no change (or every request failed) since
        # the last successful scrape
        return (url, None)


# Web Delta ![](https://travis-ci.org/N-Buchanan/web_delta.svg?branch=master)

A batch web scraping library designed for use with frequently updating sites

## Installation
`$ pip install web_delta`

## Quickstart
```python
from web_delta import WebDelta

def get_top_hn_story(html):
    """You define these functions to parse the html however you want"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    top_story = soup.find(class_='storylink').text
    return top_story
    
# create a WebDelta object to register websites with
# we can optionally specify any of these arguments:
# rate_limit -- RateLimit object. Only used for the time to pause between executions
#                when get_continuous_all or get_continuous_new is called. (default 10 minutes)
# retry_limit -- The number of times to retry a request if the registered function returns None.
#                 (default 5)
# wait_between_retries -- Whether or not to wait between retries when the registered
#                          function returns None. (default True)
# cache_file -- String. The name of the file to store the cache in. (default None)

delta = WebDelta()
# register as many websites as you want
delta.register('http://icanhazip.com', (lambda x: x.strip())) # returns your external ip
delta.register('http://news.ycombinator.com', get_top_hn_story)

# you can even register multiple functions with the same url
delta.register('http://news.ycombinator.com', get_second_hn_story) 


# now we'll process our results. Note that get_new will only return results not found in the cache
# if you want all results including those in the cache use get_all()
for result in delta.get_new():
    print(result)
 
 # results are returned as tuples of (registered site, return value of registered function)
 # for example: ('http://icanhazip.com', 'redacted')
 
 
 # You can also use web_delta to continuously watch a site (or group of sites) for changes
 # let's process all of the top hacker news stories until we get bored
 
 # we pass a RateLimit object to the WebDelta constructor that will limit our calls to hacker news
 # to one per minute. We want to be polite after all.
 from web_delta import RateLimit
 delta = WebDelta(rate_limit=RateLimit(0,1,0,0))
 
 delta.register('http://news.ycombinator.com', get_top_hn_story)
 
 # create a queue to allow us to get results back from web_delta
 from queue import Queue
 queue = Queue()
 
 # This will spawn a new thread that continuously checks the hacker news site for changes and places
 # new results in the queue for us to process.
 delta.get_continuous_new(queue) # we could alternatively use get_continuous_all()
 
 try:
    while True:
        print(queue.get())
 except KeyboardInterrupt:
    delta.stop() # stop the web_delta thread
 

```

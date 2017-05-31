from web_delta.web_delta import WebDelta, RateLimit
import unittest
import os
import pickle
import threading
from flask import Flask
import logging
from queue import Queue

# set up flask app for testing
app = Flask(__name__)

@app.route('/static')
def index():
    return 'static'

@app.route('/changes')
def changes():
    changes.counter += 1
    return 'changes {}'.format(changes.counter)

@app.route('/fail')
def fail():
    if fail.counter < 1:
        fail.counter += 1
        return 'None'
    return 'fail'

changes.counter = 0
fail.counter = 0

# suppress flask logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)


def fake_parse(html):
    """
        Stand-in for a parse function
    """
    return html


def fail_parse(html):
    if 'None' in html:
        return None
    return html


class TestWebDelta(unittest.TestCase):
    """
        Tests for the WebDelta library
    """

    @classmethod
    def setUpClass(cls):
        """
            open test flask app in another thread
        """
        t = threading.Thread(target=app.run)
        t.daemon = True # stop flask when tests are done
        t.start()


    def setUp(self):
        """
            Create cache file that we will use in our tests
        """

        cache = {}
        cache[('http://localhost:5000/static', fake_parse.__name__)] = 'static'
        cache[('http://localhost:5000/changes', fake_parse.__name__)] = ''

        # write cache file
        with open('test.cache', 'wb') as handle:
            pickle.dump(cache, handle, protocol=pickle.HIGHEST_PROTOCOL)


    def tearDown(self):
        """
            Undo any changes we've made to the cache file
        """
        try:
            os.remove('test.cache')
        except FileNotFoundError:
            # we wanted it gone anyway
            pass


    def test_one_site(self):
        """
            Test a single registered site
        """
        delta = WebDelta()
        delta.register('http://localhost:5000/static', fake_parse)

        result = delta.get_all()
        self.assertEqual(result[0][1], 'static')
        self.assertEqual(len(result), 1)


    def test_url_matches(self):
        """
            Test that the urls returned match the ones registered
        """
        delta = WebDelta()
        sites = ['http://localhost:5000/static', 'http://localhost:5000/changes']
        for site in sites:
            delta.register(site, fake_parse)

        for result in delta.get_all():
            self.assertIn(result[0], sites)

    def test_only_changes(self):
        """
            Test that calling get_new only returns results that have changed
        """
        delta = WebDelta(cache_file='test.cache')
        delta.register('http://localhost:5000/static', fake_parse)
        delta.register('http://localhost:5000/changes', fake_parse)
        
        result = delta.get_new()
        self.assertEqual(result[0][0], 'http://localhost:5000/changes')
        self.assertEqual(len(result), 1)


    def test_clear(self):
        """
            Test that clearing the tasks actually works
        """

        delta = WebDelta(cache_file='test.cache')
        delta.register('http://localhost:5000/static', fake_parse)
        delta.register('http://localhost:5000/changes', fake_parse)
        result  = delta.get_new()
        self.assertEqual(len(result), 1)

        delta.clear_tasks()
        delta.register('http://localhost:5000/static', fake_parse)
        delta.register('http://localhost:5000/changes', fake_parse)

        result  = delta.get_new()
        self.assertEqual(len(result), 2)

    def test_new_and_all(self):
        """
            Test that get_all and get_new return the same thing if there isn't a cache file
        """

        delta = WebDelta()
        delta.register('http://localhost:5000/static', fake_parse)
        delta.register('http://localhost:5000/changes', fake_parse)

        new_results = delta.get_new()
        all_results = delta.get_all() 

        self.assertEqual(len(new_results), len(all_results))


    def test_rate_limit(self):
        """
            Test that the RateLimit object is correctly used
        """
        delta = WebDelta(rate_limit=RateLimit(1,1,1,1))
        self.assertEqual(delta.rate_limit, 1 + 60 + 60 * 60 + 60 * 60 * 24)


    def test_default_rate_limit(self):
        """
            Test that the default rate limit is set properly
        """
        delta = WebDelta()
        self.assertEqual(delta.rate_limit, 60)

    
    def test_continuous_new(self):
        """
            Test that get_continuous_new adds new results to the queue and doesn't
            include results already in the cache
        """

        delta = WebDelta(rate_limit=RateLimit(1,0,0,0), cache_file='test.cache')
        delta.register('http://localhost:5000/static', fake_parse)
        delta.register('http://localhost:5000/changes', fake_parse)

        queue = Queue()
        delta.get_continuous_new(queue)

        old = ''
        new = ''
        for i in range(5):
            new = queue.get()
            self.assertNotEqual(new, old)
            old = new
        delta.stop()

    def test_continuous_all(self):
        """
            Test that get_continuous_all addes new results to the queue and includes
            results already in the cache
        """
        delta = WebDelta(rate_limit=RateLimit(1,0,0,0), cache_file='test.cache')
        delta.register('http://localhost:5000/static', fake_parse)
        delta.register('http://localhost:5000/changes', fake_parse)

        queue = Queue()
        delta.get_continuous_all(queue)

        results = []
        for i in range(5):
            results.append(queue.get()[1]) # only care about the results, not the sites

        delta.stop()

        self.assertIn('static', results)


    def test_failed_response(self):
        """
            Test that the request is retried upon failure
        """
        delta = WebDelta()
        delta.register('http://localhost:5000/fail', fail_parse)

        result = delta.get_all()
        self.assertEqual(result[0][1], 'fail')



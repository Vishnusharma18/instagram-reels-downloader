import unittest
from app import app, DOWNLOAD_DIR
import os

class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_ping(self):
        response = self.app.get('/ping')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})

    def test_index_get(self):
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Video & Shorts Downloader', response.data)
        self.assertIn(b'720p', response.data)

    def test_index_post_empty_url(self):
        response = self.app.post('/', data={'url': '', 'quality': '720p'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Please enter a valid HTTP or HTTPS URL', response.data)

    def test_index_post_invalid_url_scheme(self):
        response = self.app.post('/', data={'url': 'ftp://invalid-url.com', 'quality': '720p'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Please enter a valid HTTP or HTTPS URL', response.data)

if __name__ == '__main__':
    unittest.main()

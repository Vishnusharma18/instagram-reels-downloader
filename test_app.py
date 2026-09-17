import unittest
from app import app, DOWNLOAD_DIR
import os
import shutil

class AppTestCase(unittest.TestCase):
    def setUp(self):
        """Set up the test client and ensure the app is in testing mode."""
        self.app = app.test_client()
        self.app.testing = True

    def tearDown(self):
        """Clean up the DOWNLOAD_DIR after each test."""
        if os.path.exists(DOWNLOAD_DIR):
            shutil.rmtree(DOWNLOAD_DIR)

    def test_ping(self):
        """Test the /ping endpoint."""
        response = self.app.get('/ping')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})

    def test_index_get(self):
        """Test the GET request to the / endpoint."""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Video & Shorts Downloader', response.data)
        self.assertIn(b'720p', response.data)

    def test_index_post_empty_url(self):
        """Test the POST request to / with an empty URL."""
        response = self.app.post('/', data={'url': '', 'quality': '720p'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Please enter a valid HTTP or HTTPS URL', response.data)

    def test_index_post_invalid_url(self):
        """Test the POST request to / with an invalid URL."""
        response = self.app.post('/', data={'url': 'invalid-url', 'quality': '720p'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Please enter a valid HTTP or HTTPS URL', response.data)

    def test_index_post_missing_quality(self):
        """Test the POST request to / with a missing quality."""
        response = self.app.post('/', data={'url': 'https://example.com/video', 'quality': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Please select a valid quality option', response.data)

    def test_index_post_valid_request(self):
        """Test the POST request to / with valid data."""
        # Mocking the actual download process would be ideal here
        response = self.app.post('/', data={'url': 'https://example.com/video', 'quality': '720p'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Download started', response.data)

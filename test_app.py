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

    def test_invalid_url_domain(self):
        response = self.app.post('/', data={'url': 'https://example.com/video', 'quality': '720p'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Please enter a valid YouTube or Instagram URL.', response.data)

    def test_youtube_public_720p(self):
        response = self.app.post('/', data={'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'quality': '720p'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'video/mp4')

    def test_youtube_audio_mp3(self):
        response = self.app.post('/', data={'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'quality': 'audio'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'audio/mpeg')

    def test_unavailable_video_url(self):
        response = self.app.post('/', data={'url': 'https://www.youtube.com/watch?v=00000000000', 'quality': '720p'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'unavailable', response.data.lower())

if __name__ == '__main__':
    unittest.main()

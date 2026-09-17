import unittest
from app import app, DOWNLOAD_DIR
import os
import shutil


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def tearDown(self):
        if os.path.exists(DOWNLOAD_DIR):
            shutil.rmtree(DOWNLOAD_DIR)

    def test_ping(self):
        response = self.app.get("/ping")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})

    def test_index_get(self):
        response = self.app.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ClipFetch", response.data)
        self.assertIn(b"720p", response.data)

    def test_index_post_empty_url(self):
        response = self.app.post("/", data={"url": "", "quality": "720p"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Please paste a valid Instagram or YouTube link.", response.data)

    def test_index_post_invalid_url(self):
        response = self.app.post("/", data={"url": "invalid-url", "quality": "720p"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Please paste a valid Instagram or YouTube link.", response.data)

    def test_index_post_invalid_quality(self):
        response = self.app.post("/", data={"url": "https://example.com/video", "quality": "4k"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Please select a valid quality option.", response.data)

    def test_index_post_unsupported_url(self):
        response = self.app.post("/", data={"url": "https://example.com/video", "quality": "720p"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="alert"', response.data)


if __name__ == "__main__":
    unittest.main()

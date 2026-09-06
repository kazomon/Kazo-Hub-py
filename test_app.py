import unittest

from app import is_allowed_thumbnail_url, parse_search_results, thumbnail_proxy_url


class BackendTest(unittest.TestCase):
    def test_parse_search_results(self) -> None:
        html = """
        <ul>
          <li class="videoblock">
            <span class="title"><a href="/view_video.php?viewkey=abc"> Example title </a></span>
            <img data-src="https://i.phncdn.com/video.jpg" />
            <span class="duration">1:23</span>
            <span class="views">10K views</span>
          </li>
        </ul>
        """
        results = parse_search_results(html)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Example title")
        self.assertEqual(results[0]["url"], "https://jp.pornhub.com/view_video.php?viewkey=abc")
        self.assertEqual(results[0]["thumbnailUrl"], "/api/thumbnail?url=https%3A%2F%2Fi.phncdn.com%2Fvideo.jpg")
        self.assertEqual(results[0]["duration"], "1:23")

    def test_parse_search_results_preserves_fallback_host(self) -> None:
        html = """
        <li class="videoblock">
          <span class="title"><a href="/view_video.php?viewkey=fallback">Fallback title</a></span>
          <img data-src="https://i.phncdn.com/fallback.jpg" />
        </li>
        """
        results = parse_search_results(html, "https://www.pornhub.com")
        self.assertEqual(results[0]["url"], "https://www.pornhub.com/view_video.php?viewkey=fallback")

    def test_thumbnail_ssrf_allowlist(self) -> None:
        self.assertTrue(is_allowed_thumbnail_url("https://phncdn.com/image.jpg"))
        self.assertTrue(is_allowed_thumbnail_url("https://cdn.phncdn.com/image.jpg"))
        self.assertFalse(is_allowed_thumbnail_url("http://cdn.phncdn.com/image.jpg"))
        self.assertFalse(is_allowed_thumbnail_url("https://example.com/image.jpg"))
        self.assertIsNone(thumbnail_proxy_url("https://example.com/image.jpg"))


if __name__ == "__main__":
    unittest.main()

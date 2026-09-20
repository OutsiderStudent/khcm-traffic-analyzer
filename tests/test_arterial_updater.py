import json
import unittest

from arterial_analysis.updater import RELEASES_URL, parse_release, version_tuple


class ArterialUpdaterTest(unittest.TestCase):
    def test_version_tuple(self):
        self.assertEqual(version_tuple("v1.3.0"), (1, 3, 0))
        self.assertGreater(version_tuple("1.10.0"), version_tuple("1.3.9"))
        self.assertIsNone(version_tuple("1.3"))

    def test_parse_release(self):
        release = parse_release(json.dumps({
            "tag_name": "v1.4.0",
            "name": "KHCM Traffic Analyzer v1.4.0",
            "body": "changes",
            "html_url": "https://example.test/release",
        }))
        self.assertEqual(release.version, "1.4.0")
        self.assertEqual(release.notes, "changes")
        self.assertEqual(release.page_url, "https://example.test/release")

    def test_parse_release_uses_fallback_url(self):
        release = parse_release(json.dumps({"tag_name": "v1.3.0"}))
        self.assertEqual(release.page_url, RELEASES_URL)

    def test_invalid_tag_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_release(json.dumps({"tag_name": "latest"}))


if __name__ == "__main__":
    unittest.main()

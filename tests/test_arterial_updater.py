import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from arterial_analysis.updater import RELEASES_URL, ReleaseInfo, UpdateController, parse_release, update_helper_script, version_tuple


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
            "assets": [{
                "name": "KHCM-Traffic-Analyzer_v1.4.0.exe",
                "browser_download_url": "https://example.test/app.exe",
                "digest": "sha256:" + "a" * 64,
                "size": 123,
            }],
        }))
        self.assertEqual(release.version, "1.4.0")
        self.assertEqual(release.notes, "changes")
        self.assertEqual(release.page_url, "https://example.test/release")
        self.assertEqual(release.asset_url, "https://example.test/app.exe")
        self.assertEqual(release.digest, "sha256:" + "a" * 64)

    def test_parse_release_uses_fallback_url(self):
        release = parse_release(json.dumps({
            "tag_name": "v1.3.0",
            "assets": [{"name": "KHCM-Traffic-Analyzer_v1.3.0.exe"}],
        }))
        self.assertEqual(release.page_url, RELEASES_URL)

    def test_invalid_tag_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_release(json.dumps({"tag_name": "latest"}))

    def test_expected_exe_is_required(self):
        with self.assertRaises(ValueError):
            parse_release(json.dumps({"tag_name": "v1.4.1", "assets": []}))

    def test_download_digest_is_verified(self):
        payload=b"verified updater payload"
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"update.exe.part";path.write_bytes(payload)
            release=ReleaseInfo("1.4.1","title","notes","page","asset","sha256:"+hashlib.sha256(payload).hexdigest(),len(payload))
            UpdateController._verify_download(path,release)
            bad=ReleaseInfo("1.4.1","title","notes","page","asset","sha256:"+"0"*64,len(payload))
            with self.assertRaises(ValueError):UpdateController._verify_download(path,bad)

    def test_update_helper_preserves_original_exe_path(self):
        script=update_helper_script()
        self.assertIn("-Destination $OldExe -Force",script)
        self.assertIn("Start-Process -FilePath $OldExe",script)
        self.assertIn("Start-Process -FilePath $FallbackExe",script)

    def test_update_helper_resets_pyinstaller_environment_before_restart(self):
        script=update_helper_script()
        reset=script.index("PYINSTALLER_RESET_ENVIRONMENT")
        self.assertLess(reset,script.index("Start-Process -FilePath $OldExe"))
        self.assertLess(reset,script.index("Start-Process -FilePath $FallbackExe"))
        self.assertIn("Env:_PYI_APPLICATION_HOME_DIR",script)
        self.assertIn("Env:_MEIPASS2",script)


if __name__ == "__main__":
    unittest.main()

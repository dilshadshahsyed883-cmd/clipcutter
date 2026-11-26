import json
import unittest
from unittest.mock import patch
from deploy.drive_intake_bridge import Drive

class DriveMetadataTests(unittest.TestCase):
    def test_md5_key_case(self):
        drive = Drive("gdrive", "/tmp")
        digest = "df51385bd8abe2ae54dfbf6af72a9819"
        for key in ("md5", "MD5"):
            with self.subTest(key=key):
                entry = {"Name":"test.mp4","ID":"abcdefghijk","Size":7049848,
                         "Hashes":{key:digest}}
                with patch.object(drive,"execute",return_value=json.dumps([entry]).encode()):
                    rows=drive.scan("https://drive.google.com/drive/folders/abcdefghijk","video")
                self.assertEqual(rows[0]["md5"],digest)
                self.assertEqual(rows[0]["size"],7049848)

    def test_missing_hash_still_rejected(self):
        drive=Drive("gdrive","/tmp")
        entry={"Name":"test.mp4","ID":"abcdefghijk","Size":7049848,"Hashes":{}}
        with patch.object(drive,"execute",return_value=json.dumps([entry]).encode()):
            with self.assertRaises(ValueError):
                drive.scan("https://drive.google.com/drive/folders/abcdefghijk","video")

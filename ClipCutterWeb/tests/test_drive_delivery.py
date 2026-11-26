import hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app.modules.studio.drive_delivery import deliver_one,DeliveryError,verify_remote
from app.modules.studio.store import Store
from test_gpu_dispatch import request

class DriveDeliveryTests(unittest.TestCase):
    def test_verified_receipt_and_ambiguous_write(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();s=Store("owner",root);jid=s.create(request())["id"]
            dest=root/"out";dest.mkdir();data=b"verified artifact";(dest/"a.json").write_bytes(data)
            item={"name":"a.json","size":len(data),"sha256":hashlib.sha256(data).hexdigest()}
            folder="https://drive.google.com/drive/folders/abcdef123456789"
            with patch("app.modules.studio.drive_delivery.settings"),patch("app.modules.studio.drive_delivery.verify_remote",return_value=False),patch("app.modules.studio.drive_delivery.call",side_effect=DeliveryError("interrupted")) as call:
                with self.assertRaises(DeliveryError):deliver_one(s,jid,folder,dest,[item])
                with self.assertRaisesRegex(DeliveryError,"Unconfirmed prior upload"):deliver_one(s,jid,folder,dest,[item])
                self.assertEqual(call.call_count,1)
            with patch("app.modules.studio.drive_delivery.settings"),patch("app.modules.studio.drive_delivery.verify_remote",return_value=True),patch("app.modules.studio.drive_delivery.call") as call:
                self.assertFalse(deliver_one(s,jid,folder,dest,[item]))
                self.assertTrue(deliver_one(s,jid,folder,dest,[item]))
                call.assert_not_called()
    def test_metadata_mismatch_rejected(self):
        item={"size":5}
        with patch("app.modules.studio.drive_delivery.listing",return_value=[{"Name":"file","IsDir":False,"Size":5,"Hashes":{"MD5":"bad"}}]):
            with self.assertRaises(DeliveryError):verify_remote("folder","file",item,"good")

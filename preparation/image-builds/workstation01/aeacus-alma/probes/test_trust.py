import base64
import hashlib
import unittest
from trust import certificate_absent


class TrustTests(unittest.TestCase):
    def test_fingerprint_specific_detection_ignores_certificate_name(self):
        der=b'synthetic certificate bytes'
        pem='-----BEGIN CERTIFICATE-----\n'+base64.b64encode(der).decode()+'\n-----END CERTIFICATE-----\n'
        fp=hashlib.sha256(der).hexdigest()
        self.assertFalse(certificate_absent(pem,fp))
        self.assertTrue(certificate_absent(pem,'a'*64))

    def test_command_errors_empty_bundle_and_malformed_pem_fail_closed(self):
        for value in (None,'','garbage','-----BEGIN CERTIFICATE-----\n!!!!\n-----END CERTIFICATE-----'):
            self.assertFalse(certificate_absent(value,'a'*64))
        self.assertFalse(certificate_absent('anything','bad fingerprint'))



    def test_relocated_probe_does_not_require_organizer_certificate_file(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        import tempfile,trust
        from pathlib import Path
        pem='-----BEGIN CERTIFICATE-----\n'+base64.b64encode(b'other retained CA').decode()+'\n-----END CERTIFICATE-----\n'
        def extract(args):
            Path(args[-1]).write_text(pem)
            return SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as folder,patch.object(trust,'__file__',str(Path(folder)/'probes/trust.py')),patch.object(trust,'run',side_effect=extract):
            self.assertTrue(trust.check(11))

if __name__=='__main__':
    unittest.main()

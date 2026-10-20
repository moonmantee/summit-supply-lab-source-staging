import unittest
import ssl
from unittest.mock import Mock,patch
import inject_services

class MailTests(unittest.TestCase):
    def test_tls_failure_closes_raw_socket(self):
        imap=object.__new__(inject_services.DirectIMAP)
        imap.address='10.77.30.30'; imap.host='webmail.corp.summit.test'; imap.port=993; imap.ssl_context=Mock()
        imap.ssl_context.wrap_socket.side_effect=ssl.SSLCertVerificationError('wrong name')
        raw=Mock()
        with patch('socket.create_connection',return_value=raw):
            with self.assertRaises(ssl.SSLCertVerificationError): imap._create_socket(5)
        raw.close.assert_called_once()

    def test_tls_failure_never_sends_credentials(self):
        service={'probe':'mail_alias','host':'10.77.30.30','server_name':'webmail.corp.summit.test','ca_file':'/private/mail.crt','username':'operations@Summit','password':'private-fixture','recipient':'dispatch@corp.summit.test'}
        smtp=Mock(); smtp.starttls.side_effect=ssl.SSLCertVerificationError('private-fixture')
        with patch('inject_services.ssl.create_default_context'),patch('inject_services.DirectSMTP') as smtp_type:
            smtp_type.return_value.__enter__.return_value=smtp
            result=inject_services.run_probe(service)
        self.assertEqual(result[0],'DOWN'); self.assertNotIn('private-fixture',str(result))
        smtp.login.assert_not_called(); smtp.sendmail.assert_not_called()

    def test_ip_connection_keeps_named_tls_identity(self):
        service={'host':'10.77.30.30','server_name':'webmail.corp.summit.test'}
        with patch('smtplib.SMTP.__init__',return_value=None) as smtp_init:
            smtp=inject_services.DirectSMTP(service)
            smtp_init.assert_called_once_with('webmail.corp.summit.test',587,timeout=5)
        smtp.source_address=None
        with patch('socket.create_connection') as connect:
            smtp._get_socket('webmail.corp.summit.test',587,5)
            connect.assert_called_once_with(('10.77.30.30',587),5,None)
        imap=object.__new__(inject_services.DirectIMAP)
        imap.address='10.77.30.30'; imap.host='webmail.corp.summit.test'; imap.port=993; imap.ssl_context=Mock()
        with patch('socket.create_connection',return_value='raw') as connect:
            imap._create_socket(5)
            connect.assert_called_once_with(('10.77.30.30',993),5)
            imap.ssl_context.wrap_socket.assert_called_once_with('raw',server_hostname='webmail.corp.summit.test')

    def test_mail_login_separate_from_sender_and_no_dns_dependency(self):
        service={'host':'10.77.30.30','server_name':'webmail.corp.summit.test','ca_file':'/private/mail.crt','username':'operations@Summit','password':'private-fixture','sender':'operations@corp.summit.test','recipient':'dispatch@corp.summit.test'}
        smtp=Mock(); imap=Mock(); imap.uid.side_effect=[('OK',[b'42']),('OK',[])]; imap.select.return_value=('OK',[])
        with patch('inject_services.ssl.create_default_context'),patch('inject_services.DirectSMTP') as smtp_type,patch('inject_services.DirectIMAP') as imap_type,patch('socket.gethostbyname_ex',side_effect=AssertionError('No DNS dependency')):
            smtp_type.return_value.__enter__.return_value=smtp
            imap_type.return_value.__enter__.return_value=imap
            self.assertEqual(inject_services.mail_alias(service)[0],'PASS')
            smtp.login.assert_called_once_with('operations@Summit','private-fixture')
            self.assertEqual(smtp.sendmail.call_args.args[:2],('operations@corp.summit.test','dispatch@corp.summit.test'))
            imap.login.assert_called_once_with('operations@Summit','private-fixture')
            self.assertEqual(imap.uid.call_args_list[-1].args,('store',b'42','+FLAGS.SILENT','(\\Deleted)'))

if __name__=='__main__': unittest.main()

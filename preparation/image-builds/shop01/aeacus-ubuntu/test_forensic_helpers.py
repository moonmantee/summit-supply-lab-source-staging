import unittest
from forensic_helpers import desktop_entry


class ShortcutTests(unittest.TestCase):
    def test_each_icon_opens_its_own_editable_question_with_installed_editor(self):
        for number in (1,2,3):
            entry=desktop_entry(number)
            self.assertIn('Exec=/usr/bin/gnome-text-editor /srv/summit-shop01-forensics/Forensic-Question-%d.txt\n'%number,entry)
            self.assertIn('Type=Application\n',entry)
        for bad in (0,4,'1',True):
            with self.assertRaises(ValueError): desktop_entry(bad)

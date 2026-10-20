"""Organizer-only migration and rehearsal helpers; never publish the solution key."""
SOLUTIONS={38:'198.51.100.77',39:'/training-fixtures/public-backup.sql',40:'summit-shop-marker.service'}


def desktop_entry(number):
    if type(number) is not int or number not in (1,2,3): raise ValueError('Invalid question')
    return ('[Desktop Entry]\nType=Application\nName=Forensic Question %d\n'
            'Comment=Shop01 synthetic incident question\nIcon=accessories-text-editor\n'
            'Exec=/usr/bin/gnome-text-editor /srv/summit-shop01-forensics/Forensic-Question-%d.txt\n'
            'Terminal=false\n')%(number,number)

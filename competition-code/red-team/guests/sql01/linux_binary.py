"""Only dedicated Apache/MariaDB binaries on the matching lab guest."""
import os,pathlib,socket
from binary_rename import RenameFault
TARGETS={
 'apache_backend':('shop01','/usr/sbin/apache2','f34995f3f308dfad3e93dcf191a937cdc45847881a1a85a79fc93f5c5e1b5bb4'),
 'mariadb_backend':('sql01','/usr/sbin/mariadbd','99e73e260c9958b788753d4249592c1f2a38dba1a33444d926ea18c67e3187c2')}
def current(module):
    if module not in TARGETS:raise ValueError('Unapproved executable adapter')
    host,path,digest=TARGETS[module]
    if os.geteuid()!=0 or socket.gethostname()!=host:raise ValueError('Wrong privileged guest')
    return RenameFault(path,pathlib.Path('/var/lib/summit-caldera-business/hour4')/host)
def capture(module):
    fault=current(module);fault.protected(fault.state.parent.parent,True,True)
    for directory in (fault.state.parent,fault.state):
        if directory.exists() or directory.is_symlink():fault.protected(directory,True,True)
        else:directory.mkdir(mode=0o700)
    fault.capture(TARGETS[module][2])

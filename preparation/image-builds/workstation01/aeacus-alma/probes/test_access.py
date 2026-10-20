import unittest
from access import settings, pam_line, password_ok, ssh_allowed, sudo_safe, firewall_safe, sudo_denied, competitor_sudo_ok


class AccessTests(unittest.TestCase):
    def test_firewall_rejects_alternate_sources_and_modified_builtin_policy(self):
        from unittest.mock import patch
        from access import firewall_check
        rich='\n'.join('rule family="ipv6" icmp-type name="'+kind+'" accept' for kind in ('neighbour-advertisement','neighbour-solicitation','router-advertisement','redirect','mld-listener-done','mld-listener-query','mld-listener-report','mld2-listener-report'))
        data={'--get-zone-of-interface=ens160':'summit-workstation','--get-zones':'summit-workstation public',
              '--get-target':'default','--list-services':'ssh dhcpv6-client','--list-ports':'','--list-rich-rules':'',
              '--list-forward-ports':'','--list-sources':'','--list-protocols':'','--get-all-rules':'','--get-policies':'allow-host-ipv6'}
        policy={'--get-target':'CONTINUE','--get-priority':'-15000','--list-ingress-zones':'ANY','--list-egress-zones':'HOST',
                '--list-services':'','--list-ports':'','--list-protocols':'','--list-forward-ports':'','--list-rich-rules':rich}
        source=['']; other_interface=['']; policy_port=['']
        def query(args):
            key=args[-1]
            if key=='--get-target' and '--permanent' not in args: return None
            if key=='--list-all':
                return 'allow-host-ipv6 (active)\n  priority: -15000\n  target: CONTINUE\n' if '--policy=allow-host-ipv6' in args else 'summit-ws01 (active)\n  target: default\n'
            if '--policy=allow-host-ipv6' in args:
                return policy_port[0] if key=='--list-ports' else policy.get(key)
            if '--zone=public' in args and key=='--list-sources': return source[0]
            if key=='--list-interfaces': return other_interface[0] if '--zone=public' in args else 'ens160'
            return data.get(key)
        with patch('access.unit_ready',return_value=True),patch('access.successful',side_effect=query):
            self.assertTrue(firewall_check())
            source[0]='10.77.0.0/16'; self.assertFalse(firewall_check()); source[0]=''
            other_interface[0]='ens192'; self.assertFalse(firewall_check()); other_interface[0]=''
            policy_port[0]='1-65535/tcp'; self.assertFalse(firewall_check())

    def test_domain_sudo_checks_require_both_admins_and_do_not_target_fallback(self):
        good='Matching Defaults entries:\n timestamp_timeout=5\nSudoers entry:\n Options: authenticate\n Commands:\n ALL\n'
        users={'alex.admin@corp.summit.test':good,'taylor.admin@corp.summit.test':good}
        self.assertTrue(competitor_sudo_ok(users,20))
        self.assertTrue(competitor_sudo_ok(users,21))
        self.assertFalse(competitor_sudo_ok({'competitor-recovery':good},20))
        self.assertFalse(competitor_sudo_ok({'alex.admin@corp.summit.test':good},20))
        users['taylor.admin@corp.summit.test']=good.replace('authenticate','!authenticate').replace('timestamp_timeout=5','timestamp_timeout=60')
        self.assertFalse(competitor_sudo_ok(users,20))
        self.assertFalse(competitor_sudo_ok(users,21))

    def test_explicit_sudo_denial_can_return_zero_but_errors_cannot_pass(self):
        message='User summit-employee is not allowed to run sudo on workstation01.\n'
        self.assertTrue(sudo_denied(0,message,'','summit-employee'))
        self.assertTrue(sudo_denied(1,message,'','summit-employee'))
        self.assertFalse(sudo_denied(0,'','', 'summit-employee'))
        self.assertFalse(sudo_denied(1,'','sudo: account validation failure','summit-employee'))
        self.assertFalse(sudo_denied(0,message+'Sudoers entry:\n Commands: ALL','','summit-employee'))
        self.assertFalse(sudo_denied(0,message,'','summit-auditor'))
        self.assertFalse(sudo_denied(2,message,'','summit-employee'))

    def test_configuration_precedence_and_comments(self):
        self.assertEqual(settings(['minlen=16\n# minlen=2','minlen=8'])['minlen'],'8')
        self.assertIsNone(settings(['broken line with spaces']))

    def test_pam_optional_and_early_bypass_do_not_enforce(self):
        good='password requisite pam_pwquality.so local_users_only\npassword sufficient pam_unix.so use_authtok'
        self.assertIsNotNone(pam_line(good,'password','pam_pwquality.so'))
        self.assertIsNone(pam_line(good.replace('requisite','optional'),'password','pam_pwquality.so'))
        self.assertIsNone(pam_line('password sufficient pam_permit.so\n'+good,'password','pam_pwquality.so'))

    def test_minimum_length_accounts_for_character_credits_and_pam_override(self):
        line={'local_users_only':'1'}
        cfg={'minlen':'14','enforcing':'1','dcredit':'0','ucredit':'0','lcredit':'0','ocredit':'0'}
        self.assertTrue(password_ok(1,line,cfg))
        self.assertFalse(password_ok(1,line,dict(cfg,enforcing='0')))
        self.assertFalse(password_ok(1,dict(line,minlen='8'),cfg))
        self.assertFalse(password_ok(1,line,dict(cfg,dcredit='1')))
        self.assertFalse(password_ok(2,line,dict(cfg,enforcing='0')))
        self.assertFalse(password_ok(2,{},cfg))

    def test_ssh_allowlist_rejects_wildcards_and_preserves_organizer(self):
        good='allowgroups jwang competitor-recovery linux-workstation-admins@corp.summit.test\n'
        self.assertTrue(ssh_allowed('hostkey /etc/ssh/ssh_host_rsa_key\nhostkey /etc/ssh/ssh_host_ed25519_key\n'+good,True))
        self.assertTrue(ssh_allowed('allowgroups jwang\nallowgroups competitor-recovery\nallowgroups linux-workstation-admins@corp.summit.test\n',True))
        self.assertTrue(ssh_allowed(good,True))
        self.assertFalse(ssh_allowed('allowusers jwang\n',True))
        self.assertFalse(ssh_allowed(good.replace('competitor-recovery','wheel'),True))
        self.assertFalse(ssh_allowed(good+'allowusers jwang\n',True))
        self.assertFalse(ssh_allowed(good+'denygroups competitor-recovery\n',True))
        self.assertFalse(ssh_allowed(good.replace('linux-workstation-admins@corp.summit.test','*'),True))
        self.assertFalse(ssh_allowed('allowusers *\n',True))
        self.assertFalse(ssh_allowed('allowusers summit-unknown\n',True))
        self.assertFalse(ssh_allowed('allowusers jwang\ndenyusers jwang\n',True))
        self.assertFalse(ssh_allowed(None,True))

    def test_sudo_verbose_all_entries_must_require_authentication(self):
        good='Matching Defaults entries for summit-admin on workstation01:\n    timestamp_timeout=5\n\nSudoers entry:\n    RunAsUsers: root\n    Options: authenticate\n    Commands:\n        /usr/bin/id\n'
        self.assertTrue(sudo_safe(good,20))
        self.assertFalse(sudo_safe(good+'\nSudoers entry:\n    Options: !authenticate\n    Commands:\n        ALL\n',20))
        self.assertTrue(sudo_safe(good,21))
        self.assertFalse(sudo_safe(good.replace('timestamp_timeout=5','timestamp_timeout=-1'),21))
        self.assertFalse(sudo_safe(good.replace('timestamp_timeout=5','timestamp_timeout=60'),21))
        self.assertFalse(sudo_safe('',20))

    def test_firewall_accept_or_extra_permissions_cannot_pass(self):
        good={'target':'default','services':['ssh','dhcpv6-client'],'ports':[],'rich_rules':[],'forward_ports':[],'sources':[],'protocols':[]}
        self.assertTrue(firewall_safe(good))
        self.assertFalse(firewall_safe(dict(good,target='ACCEPT')))
        self.assertFalse(firewall_safe(dict(good,services=['ssh','cockpit'])))
        self.assertFalse(firewall_safe(dict(good,ports=['1-65535/tcp'])))
        self.assertFalse(firewall_safe({}))


if __name__=='__main__':
    unittest.main()

import unittest
import defense

class DefenseTests(unittest.TestCase):
    def test_native_ipv6_routing_guard_does_not_block_plain_tcp_and_icmp_aliases_match(self):
        base=':INPUT DROP [0:0]\n-A INPUT -j ufw6-before-input\n-A ufw6-before-input -m rt --rt-type 0 -j DROP\n-A ufw6-before-input -p ipv6-icmp -m icmp6 --icmpv6-type 129 -j ACCEPT\n-A ufw6-before-input -j ufw6-user-input\n'
        for port in ('80','443'): base+='-A ufw6-user-input -p tcp --dport '+port+' -j ACCEPT\n'
        self.assertTrue(defense.firewall_rules_safe(base,True))
        saved=':ufw6-before-input - [0:0]\n-A ufw6-before-input -m rt --rt-type 0 -j DROP\n-A ufw6-before-input -p icmpv6 --icmpv6-type echo-reply -j ACCEPT\n'
        self.assertTrue(defense.persistent_auxiliary_match(base,saved,True))
    def test_saved_auxiliary_policy_must_match_loaded_rules(self):
        compare=getattr(defense,'persistent_auxiliary_match',lambda *_:True)
        live='-A ufw-before-input -i lo -j ACCEPT\n-A ufw-before-input -j ufw-user-input\n'
        saved=':ufw-before-input - [0:0]\n-A ufw-before-input -i lo -j ACCEPT\n'
        self.assertTrue(compare(live,saved))
        self.assertFalse(compare(live,saved+'-A ufw-before-input -j DROP\n'))
    def test_required_firewall_accepts_are_reachable_and_not_shadowed(self):
        rules=':INPUT DROP [0:0]\n-A INPUT -j ufw-before-input\n-A ufw-before-input -j ufw-user-input\n'
        for source in defense.SSH_SOURCES:
            rules+='-A ufw-user-input -s '+source+' -p tcp --dport 22 -j ACCEPT\n'
        for port in ('80','443'): rules+='-A ufw-user-input -p tcp --dport '+port+' -j ACCEPT\n'
        self.assertTrue(defense.firewall_rules_safe(rules))
        for bad in (rules.replace('-A ufw-before-input -j ufw-user-input\n',''),
                    rules.replace('-A ufw-before-input -j ufw-user-input','-A ufw-before-input -j DROP\n-A ufw-before-input -j ufw-user-input'),
                    rules.replace('-A ufw-user-input -p tcp --dport 80 -j ACCEPT','-A ufw-user-input -p tcp --dport 80 -j DROP\n-A ufw-user-input -p tcp --dport 80 -j ACCEPT')):
            self.assertFalse(defense.firewall_rules_safe(bad))

    def test_update_credit_requires_current_enabled_security_source_evidence(self):
        good={'refresh':1,'upgrade':1,'security_origin':True,'timer':True,'installed':True,'source_usable':True}
        self.assertTrue(defense.evaluate(23,good))
        self.assertFalse(defense.evaluate(23,dict(good,source_usable=False)))
    def test_rule_comparison_accepts_native_serialization_without_losing_constraints(self):
        live='-A ufw-user-input -s 10.77.30.1/32 -p tcp -m tcp --dport 22 -j ACCEPT\n'
        saved='-A ufw-user-input -p tcp --dport 22 -s 10.77.30.1 -j ACCEPT\n'
        compare=getattr(defense,'persistent_rules_match',lambda *_:False)
        self.assertTrue(compare(live,saved))
        for changed in (saved.replace('10.77.30.1','10.77.50.1'),saved.replace('22','23'),saved.replace('-j ACCEPT','--ctstate NEW -j ACCEPT'),saved.replace('-j ACCEPT','-j DROP')):
            self.assertFalse(compare(live,changed))
        self.assertFalse(compare(saved.replace('-j ACCEPT','--ctstate NEW -j ACCEPT'),saved.replace('-j ACCEPT','--ctstate NEW -j ACCEPT')))
        live6='-A ufw6-user-input -p tcp -m tcp --dport 443 -j ACCEPT\n'
        self.assertTrue(compare(live6,live6.replace(' -m tcp',''),True))

    def test_inactive_baseline_accepts_only_empty_standard_ufw_hooks(self):
        # Literal native empty scaffold, independent of the implementation.
        rules='*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\n:ufw-before-input - [0:0]\n-A INPUT -j ufw-before-input\nCOMMIT\n'
        self.assertTrue(getattr(defense,'inactive_firewall_baseline',lambda *_:False)(rules))
        for bad in (rules+'-A ufw-before-input -j ACCEPT\n',rules+'-A INPUT -j DROP\n',rules.replace('INPUT ACCEPT','INPUT DROP'),rules+'*nat\nCOMMIT\n'):
            self.assertFalse(getattr(defense,'inactive_firewall_baseline',lambda *_:False)(bad))

    def test_native_ipv6_chains_require_web_rules_and_reject_open_ssh(self):
        rules=':INPUT DROP [0:0]\n-A INPUT -j ufw6-before-input\n-A ufw6-before-input -j ufw6-user-input\n-A ufw6-before-input -p ipv6-icmp --icmpv6-type packet-too-big -j ACCEPT\n-A ufw6-user-input -p tcp -m tcp --dport 80 -j ACCEPT\n-A ufw6-user-input -p tcp -m tcp --dport 443 -j ACCEPT\n'
        self.assertTrue(defense.firewall_rules_safe(rules,True))
        self.assertFalse(defense.firewall_rules_safe(rules.replace('-A ufw6-user-input -p tcp -m tcp --dport 443 -j ACCEPT\n',''),True))
        self.assertFalse(defense.firewall_rules_safe(rules+'-A ufw6-user-input -p tcp -m tcp --dport 22 -j ACCEPT\n',True))

    def test_firewall_rejects_accept_bypass_before_user_policy(self):
        base=':INPUT DROP [0:0]\n-A INPUT -j ufw-before-input\n-A ufw-before-input -j ufw-user-input\n'
        for src in ('10.77.10.50/32','10.77.10.1/32','10.77.30.1/32','10.77.70.10/32'):
            base+='-A ufw-user-input -s '+src+' -p tcp -m tcp --dport 22 -j ACCEPT\n'
        for port in ('80','443'):
            base+='-A ufw-user-input -p tcp -m tcp --dport '+port+' -j ACCEPT\n'
        self.assertTrue(defense.firewall_rules_safe(base))
        # UFW always jumps through declared logging chains, even when empty.
        empty_chain=':ufw-before-logging-input - [0:0]\n-A INPUT -j ufw-before-logging-input\n'
        self.assertTrue(defense.firewall_rules_safe(base+empty_chain))
        self.assertFalse(defense.firewall_rules_safe(base.replace('-A ufw-user-input -s 10.77.30.1/32 -p tcp -m tcp --dport 22 -j ACCEPT\n','')))
        self.assertFalse(defense.firewall_rules_safe(base+'-A ufw-before-input -j ACCEPT\n'))
        self.assertFalse(defense.firewall_rules_safe(base+'-A ufw-before-input -j bypass\n-A bypass -j ACCEPT\n'))

    def test_security_origin_reads_list_children_and_rejects_other_vendor(self):
        good='Unattended-Upgrade::Allowed-Origins "";\nUnattended-Upgrade::Allowed-Origins:: "${distro_id}:${distro_codename}-security";'
        self.assertTrue(defense.security_origin(good))
        self.assertFalse(defense.security_origin('Unattended-Upgrade::Allowed-Origins:: "OtherVendor:noble-security";'))

    def test_active_service_is_not_active_firewall(self):
        self.assertFalse(defense.evaluate(17, {'status':'Status: inactive','persistent':'ENABLED=yes'}))
        self.assertTrue(defense.evaluate(17, {'status':'Status: active\n','persistent':'ENABLED=yes'}))
        self.assertFalse(defense.evaluate(17, {'status':'Status: active\n','persistent':'ENABLED=no'}))

    def test_apparmor_requires_selected_profile_not_some_profile(self):
        d={'profiles':{'rsyslogd':'enforce'},'running':True,'persistent_enforcing':True}
        self.assertTrue(defense.evaluate(19,d))
        d['profiles']={'rsyslogd':'complain','unrelated':'enforce'}
        self.assertFalse(defense.evaluate(19,d))

    def test_audit_runtime_and_persistent_rule_sets_both_required(self):
        rules='-w /etc/passwd -p wa -k summit_accounts\n-w /etc/group -p wa -k summit_accounts\n-w /etc/shadow -p wa -k summit_accounts\n-w /etc/sudoers -p wa -k summit_privilege\n-w /etc/sudoers.d -p wa -k summit_privilege'
        self.assertTrue(defense.evaluate(21, {'running':True,'runtime_rules':rules,'persistent_rules':rules}))
        self.assertFalse(defense.evaluate(21, {'running':True,'runtime_rules':'No rules','persistent_rules':rules}))

    def test_journal_last_storage_setting_and_persistent_evidence(self):
        self.assertTrue(defense.evaluate(22, {'policy':'[Journal]\nStorage=persistent','logs_present':True,'running':True}))
        self.assertFalse(defense.evaluate(22, {'policy':'[Journal]\nStorage=persistent\nStorage=volatile','logs_present':True,'running':True}))
        self.assertFalse(defense.evaluate(22, {'policy':'[Journal]\nStorage=persistent','logs_present':False,'running':True}))

    def test_update_settings_need_timer_and_approved_security_origin(self):
        good={'refresh':1,'upgrade':1,'security_origin':True,'timer':True,'installed':True,'source_usable':True}
        self.assertTrue(defense.evaluate(23,good))
        for key in ('timer','security_origin','installed'):
            d=dict(good); d[key]=False; self.assertFalse(defense.evaluate(23,d))

    def test_apache_hold_check_does_not_credit_uninstallation(self):
        self.assertFalse(defense.evaluate(24, {'installed':False,'holds':[]}))
        self.assertFalse(defense.evaluate(24, {'installed':True,'holds':['apache2']}))
        self.assertTrue(defense.evaluate(24, {'installed':True,'holds':[]}))

if __name__ == '__main__': unittest.main()

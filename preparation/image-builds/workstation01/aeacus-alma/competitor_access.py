"""Guard resumption of the exact pending local competitor fallback account."""
def pending_recovery_account(data):
    uid=data.get('uid'); gid=data.get('gid')
    return data.get('local') is True and data.get('name')=='competitor-recovery' and isinstance(uid,int) and uid>=1000 and isinstance(gid,int) and gid>=1000 and data.get('group_name')=='competitor-recovery' and data.get('group_gid')==gid and data.get('home')=='/home/competitor-recovery' and data.get('home_uid')==uid and data.get('home_gid')==gid and data.get('home_mode')==0o700 and data.get('home_symlink') is False and data.get('shell')=='/sbin/nologin' and data.get('grant_absent') is True and data.get('groups')==['competitor-recovery']

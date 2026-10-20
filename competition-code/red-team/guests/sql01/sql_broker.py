"""SQL-only fixed event broker, sharing the bounded peer-credential protocol."""
import argparse,json,os,pathlib,socketserver,stat
from fixture_broker import Broker,BrokerHandler
from fixture_contract import strict_json,authorization_transport
from business_worker import Worker
from business_actions import Actions,STATE
from mariadb_backend import MariaDB,private_state
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);args=p.parse_args()
    assert os.geteuid()==0
    config=strict_json(pathlib.Path(args.config).read_bytes())
    assert config['guest']=='sql01' and config['targets']=={'mariadb':'mariadb.service','desktop':'/var/lib/summit-caldera-notices','wall':'/usr/bin/wall'}
    private_state();actions=Actions(STATE/'recovery.sqlite3',MariaDB())
    def health():return config.get('business_enabled',False) and Actions(STATE/'recovery.sqlite3',MariaDB()).ready()
    broker=Broker(config,authorization_transport(config),Worker,health)
    address=pathlib.Path('/run/summit-caldera-broker/broker.sock')
    if address.is_symlink():raise ValueError('Socket replacement preserved')
    if address.exists():
        info=address.lstat()
        if info.st_uid!=0 or not stat.S_ISSOCK(info.st_mode):raise ValueError('Socket replacement preserved')
        address.unlink()
    with socketserver.UnixStreamServer(str(address),BrokerHandler) as server:
        os.chown(address,0,config['agent_gid']);address.chmod(0o660)
        server.agent_uid=config['agent_uid'];server.broker=broker;server.serve_forever(poll_interval=0.25)
if __name__=='__main__':main()

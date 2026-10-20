"""Create one stdlib-only installer that can be transferred without SSH."""
import base64
from pathlib import Path
import zlib

base = Path(__file__).resolve().parent
source = (base/'shop_probe.py').read_bytes()
template = (base/'shop_probe_installer.py').read_text()
payload = base64.b64encode(zlib.compress(source, 9)).decode('ascii')
entry = f'''if __name__ == '__main__':
    import base64
    import zlib
    try:
        raise SystemExit(main(zlib.decompress(base64.b64decode({payload!r})).decode()))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
'''
output = base/'install-shop-order-check.py'
output.write_text(template.replace('# PACKAGED_ENTRY_POINT', entry), encoding='utf-8')
(base/'team-portal-package/shop_probe.py').write_bytes(source)
print(output)

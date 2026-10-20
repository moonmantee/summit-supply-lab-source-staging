import hashlib,pathlib,sys
base=pathlib.Path("/home/jwang")
expected={'contract.py': '826402227ae384f9fb75c2ac7d065145ff4002bee5a95269dc69c1b4bbdaf3e8', 'probes.py': 'df29548142034ef5413d6540f5c65a28cbc1ee7bd3e344520a95569b5d6614b9', 'test_contract.py': '24a40501de80b8a170b42fe38a073424bc91b7b107ff04b8742f9b44cc6673a1', 'build_sql01.py': '9fc65305a9fcadb4fff68fb3246a2fa372b821b2487fc93d2c4616f3bb9ce071', 'diagnose-sql01-build.py': 'f189f323b0af7324dd78172f5db595ec3d4d05fbb36c8cf11963521a1ce93b8a'}
for name,digest in expected.items():
 p=base/name
 if p.is_symlink(): raise RuntimeError("Substituted staging path")
 if p.exists():
  if hashlib.sha256(p.read_bytes()).hexdigest()!=digest: raise RuntimeError("Changed staging file preserved: "+name)
  p.unlink()
  cache=base/"__pycache__"/(p.stem+".cpython-312.pyc")
  if cache.is_file() and not cache.is_symlink(): cache.unlink()
  print("Removed task staging: "+name)

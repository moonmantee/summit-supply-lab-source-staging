"""Diagnostic subprocess helper for commands which never receive secrets."""
import os
import subprocess


def run_package_command(args,timeout=300):
    result=subprocess.run(args,text=True,capture_output=True,timeout=timeout,env=dict(os.environ,LC_ALL='C'))
    if result.returncode:
        raise RuntimeError('Package command failed (exit %d): %s\n%s\n%s'%(result.returncode,' '.join(args),result.stdout[-5000:],result.stderr[-5000:]))
    return result

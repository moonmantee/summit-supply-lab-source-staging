import sys
import unittest
from package_tools import run_package_command


class PackageToolTests(unittest.TestCase):
    def test_failed_command_preserves_actual_diagnostics(self):
        with self.assertRaises(RuntimeError) as error:
            run_package_command([sys.executable,'-c','import sys; print("missing RPM"); print("dependency error",file=sys.stderr); sys.exit(1)'])
        self.assertIn('missing RPM',str(error.exception))
        self.assertIn('dependency error',str(error.exception))
        self.assertIn('exit 1',str(error.exception))

    def test_successful_command_preserves_query_output(self):
        result=run_package_command([sys.executable,'-c','print("package-version")'])
        self.assertEqual(result.stdout.strip(),'package-version')


if __name__=='__main__':
    unittest.main()

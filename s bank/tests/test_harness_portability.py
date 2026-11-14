"""Exercise the real web harness with a simulated Linux argv-size boundary."""
import errno
import shutil
import subprocess
import unittest
from unittest.mock import patch


class HarnessPortabilityTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_web_harness_executes_with_a_128k_argument_limit(self):
        from test_web_contract import WebContractTests

        original_run = subprocess.run

        def bounded_run(arguments, **kwargs):
            if any(len(str(argument).encode()) + 1 > 131072 for argument in arguments):
                raise OSError(errno.E2BIG, 'Argument list too long')
            return original_run(arguments, **kwargs)

        succeeded = False
        with patch('subprocess.run', side_effect=bounded_run):
            try:
                WebContractTests().node_app('')
                succeeded = True
            except OSError as error:
                if error.errno != errno.E2BIG:
                    raise
        self.assertTrue(succeeded, 'The web harness must execute under the Linux per-argument limit')

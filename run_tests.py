# run_tests.py

import unittest

if __name__ == "__main__":
    loader = unittest.TestLoader()
    tests = loader.discover("tests")
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(tests)

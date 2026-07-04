"""Top-level test configuration.

Sets RAGKIT_ENV=test for all tests so that mock guards (R2-a)
don't block test execution.
"""

import os

# Set before any imports to ensure mock guards pass
os.environ["RAGKIT_ENV"] = "test"

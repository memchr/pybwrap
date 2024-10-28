import logging


from pybwrap import Bwrap
from test_bwrap import TestBwrap

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test")


class TestBrapWithProfile(TestBwrap):
    def setUp(self):
        """Set up a Bwrap instance with default parameters for testing."""
        self.bwrap = Bwrap(
            user="testuser",
            hostname="testhost",
            profile="/profile",
            loglevel=10,
            etc_binds=("group", "passwd", "hostname"),
        )
        self.args = " ".join(self.bwrap.args)

    def test_init(self):
        self.assertIn(
            f"--bind {str(self.bwrap.profile)} {str(self.bwrap.home)}", self.args
        )

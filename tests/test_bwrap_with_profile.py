import unittest
from pathlib import Path
from pybwrap import Bwrap, BindMode


class TestBrapWithProfile(unittest.TestCase):
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
        self.assertIn(f"--bind /profile {str(self.bwrap.home)}", self.args)

    def test_home_bind(self):
        self.bwrap.home_bind(".cache")
        self.assertIn(
            f"--ro-bind-try {str(Path.home()/".cache")} {str(self.bwrap.home / ".cache")}",
            " ".join(self.bwrap.args),
        )
        self.bwrap.home_bind(".cache", "device/b", mode=BindMode.DEV)
        self.assertIn(
            f"--dev-bind-try {str(Path.home()/".cache")} {str(self.bwrap.home / "device/b")}",
            " ".join(self.bwrap.args),
        )

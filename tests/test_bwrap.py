import shutil
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from pybwrap import Bwrap, BindMode


class TestBwrap(unittest.TestCase):
    def setUp(self):
        """Set up a Bwrap instance with default parameters for testing."""
        self.bwrap = Bwrap(
            user="testuser",
            hostname="testhost",
            loglevel=10,
            etc_binds=("group", "passwd", "hostname"),
        )
        self.args = " ".join(self.bwrap.args)

    def clear_args(self):
        self.bwrap.args = []

    def test_init_env_with_default_paths(self):
        self.assertIn("--clearenv", self.bwrap.args)
        self.assertIn("--setenv HOME", self.args)
        self.assertIn("--setenv SHELL", self.args)

    def test_init_defaults(self):
        self.assertIn("--tmpfs /tmp", self.args)
        self.assertIn("--proc /proc", self.args)
        self.assertIn("--dir /var", self.args)
        self.assertIn("/etc", self.args)
        self.assertIn("--hostname testhost", self.args)

    def test_init_system_id_hostname(self):
        self.assertIn("--unshare-uts", self.args)
        self.assertIn("--hostname testhost", self.args)
        self.assertEqual(self.bwrap.hostname, "testhost")

    def test_bind(self):
        src, dest = "/src/path", "/dest/path"
        self.clear_args()
        self.bwrap.bind(src, dest, BindMode.RO)
        self.assertEqual(["--ro-bind-try", src, dest], self.bwrap.args)

    def test_symlink(self):
        self.clear_args()
        self.bwrap.symlink(("/usr/lib", "/lib"), ("/usr/bin", "/bin"))
        expected_args = [
            "--symlink",
            "/usr/lib",
            "/lib",
            "--symlink",
            "/usr/bin",
            "/bin",
        ]
        self.assertEqual(expected_args, self.bwrap.args)

    def test_unsetenv(self):
        self.clear_args()
        self.bwrap.unsetenv("VAR1", "VAR2")
        expected_args = ["--unsetenv", "VAR1", "--unsetenv", "VAR2"]
        self.assertEqual(expected_args, self.bwrap.args)

    def test_home_bind(self):
        """Test that home_bind adds the correct arguments with home-relative paths."""
        self.clear_args()
        self.bwrap.home_bind(".cache", "dest_path")
        expected_args = [
            "--ro-bind-try",
            str(Path.home() / ".cache"),
            "/home/testuser/dest_path",
        ]
        self.assertEqual(expected_args, self.bwrap.args)

    def test_file_creation(self):
        """Test file creation method to ensure args are populated with file descriptor commands."""
        content = "test content"
        dest = "/etc/testfile.conf"
        self.clear_args()
        with patch("os.pipe", return_value=(3, 4)), patch("os.write") as mock_write:
            self.bwrap.file(content, dest)
            mock_write.assert_called_once_with(4, content.encode())
            self.assertEqual(["--file", "3", dest], self.bwrap.args)

    def test_bind_relative_path_to_host_home(self):
        self.clear_args()
        self.bwrap.bind("/src", Path.home() / "dest")
        self.assertEqual(
            ["--ro-bind-try", "/src", str(self.bwrap.home / "dest")], self.bwrap.args
        )

    def test_resolve_path(self):
        home = Path.home()
        self.assertEqual(
            self.bwrap.resolve_path(str(home)),
            self.bwrap.home,
        )
        self.assertEqual(
            self.bwrap.resolve_path(str(home / "src")),
            self.bwrap.home / "src",
        )
        self.assertEqual(
            self.bwrap.resolve_path("/src"),
            Path("/src"),
        )
        self.assertEqual(
            self.bwrap.resolve_path("src"),
            Path("src"),
        )

    def test_bind_relative_path(self):
        self.clear_args()
        self.bwrap.bind("/src", "dest")
        expected_args = [
            "--ro-bind-try",
            "/src",
            str(self.bwrap.resolve_path(Path.cwd()) / "dest"),
        ]
        self.assertEqual(expected_args, self.bwrap.args)

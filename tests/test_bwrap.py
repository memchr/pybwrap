import unittest
from unittest.mock import patch
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

    def test_init_defaults(self):
        """Test the default initialization of a Bwrap instance."""
        self.assertIn("--tmpfs", self.args)
        self.assertIn("--proc", self.args)
        self.assertIn("--dir", self.args)
        self.assertIn("/etc", self.args)
        self.assertIn("--hostname testhost", self.args)

    def test_init_system_id_hostname(self):
        """Test that hostname is set correctly in self.args if different from the system hostname."""
        self.assertIn("--unshare-uts", self.args)
        self.assertIn("--hostname testhost", self.args)
        self.assertEqual(self.bwrap.hostname, "testhost")

    def test_bind_method(self):
        """Test bind method adds the correct arguments for read-only bind mode."""
        src, dest = "/src/path", "/dest/path"
        self.bwrap.bind(src, dest, BindMode.RO)
        expected_args = " ".join(["--ro-bind-try", src, dest])
        self.assertIn(expected_args, " ".join(self.bwrap.args))

    def test_symlink_method(self):
        """Test that symlink arguments are added correctly."""
        self.bwrap.symlink(("/usr/lib", "/lib"), ("/usr/bin", "/bin"))
        expected_args = [
            "--symlink",
            "/usr/lib",
            "/lib",
            "--symlink",
            "/usr/bin",
            "/bin",
        ]
        self.assertIn(" ".join(expected_args), " ".join(self.bwrap.args))

    @patch("os.getenv", return_value="/usr/bin/bash")
    def test_init_env_with_default_paths(self, mock_getenv):
        """Test that setenv appends environment variables to args."""
        self.assertIn("--clearenv", self.bwrap.args)
        self.assertIn("--setenv HOME", self.args)

    def test_unsetenv_method(self):
        """Test that unsetenv adds the correct arguments to unset environment variables."""
        self.bwrap.unsetenv("VAR1", "VAR2")
        expected_args = ["--unsetenv", "VAR1", "--unsetenv", "VAR2"]
        self.assertIn(" ".join(expected_args), " ".join(self.bwrap.args))

    @patch("os.path.exists", return_value=True)
    def test_home_bind(self, mock_exists):
        """Test that home_bind adds the correct arguments with home-relative paths."""
        self.bwrap.home_bind(".cache", "dest_path")
        expected_args = [
            "--ro-bind-try",
            str(Path.home() / ".cache"),
            "/home/testuser/dest_path",
        ]
        self.assertIn(" ".join(expected_args), " ".join(self.bwrap.args))

    def test_file_creation(self):
        """Test file creation method to ensure args are populated with file descriptor commands."""
        content = "test content"
        dest = "/etc/testfile.conf"
        with patch("os.pipe", return_value=(3, 4)), patch("os.write") as mock_write:
            self.bwrap.file(content, dest)
            mock_write.assert_called_once_with(4, content.encode())
            self.assertIn(dest, self.bwrap.args)

    def test_bind_relative_path_to_host_home(self):
        self.bwrap.bind("/src", Path.home() / "dest")
        self.assertIn(
            f"--ro-bind-try /src {str(self.bwrap.home / "dest")}",
            " ".join(self.bwrap.args),
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
        self.bwrap.bind("/src", "dest")
        self.assertIn(
            f"--ro-bind-try /src {str(self.bwrap.resolve_path(Path.cwd()) / "dest")}",
            " ".join(self.bwrap.args),
        )

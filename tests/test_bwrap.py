import unittest
from unittest.mock import patch
from pathlib import Path


from pybwrap import Bwrap, BindMode, HOME


class TestBwrap(unittest.TestCase):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.cwd = Path.cwd()

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
        self.bwrap.bind(src, dest, mode=BindMode.RO)
        self.assertEqual(["--ro-bind-try", src, dest], self.bwrap.args)
        self.clear_args()
        self.bwrap.bind(src, dest, mode=BindMode.DEV)
        self.assertEqual(["--dev-bind-try", src, dest], self.bwrap.args)

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

    def test_bind_anchor(self):
        self.clear_args()
        self.bwrap.bind(HOME / ".cache")
        self.assertEqual(
            [
                "--ro-bind-try",
                str(Path.home() / ".cache"),
                str(self.bwrap.home / ".cache"),
            ],
            self.bwrap.args,
        )

    def test_bind_anchor_home_with_dest(self):
        self.clear_args()
        self.bwrap.bind(HOME / ".cache", HOME / "device/b", mode=BindMode.DEV)
        self.assertEqual(
            [
                "--dev-bind-try",
                str(Path.home() / ".cache"),
                str(self.bwrap.home / "device/b"),
            ],
            self.bwrap.args,
        )

    def test_bind_all_anchor_home(self):
        self.clear_args()
        self.bwrap.bind_all(
            {"src": ".cache", "dest": "host_cache"},
            ".local/low",
            {"src": "bbbb", "mode": BindMode.RW},
            src_anchor=HOME,
            dest_anchor=self.bwrap.home,
        )
        expected_args = [
            "--ro-bind-try",
            str(HOME / ".cache"),
            "/home/testuser/host_cache",
            "--ro-bind-try",
            str(HOME / ".local/low"),
            "/home/testuser/.local/low",
            "--bind-try",
            str(HOME / "bbbb"),
            "/home/testuser/bbbb",
        ]
        self.assertEqual(expected_args, self.bwrap.args)

    def test_file_creation(self):
        content = "test content"
        dest = "/etc/testfile.conf"
        self.clear_args()
        with patch("os.pipe", return_value=(3, 4)), patch("os.write") as mock_write:
            self.bwrap.file(content, dest)
            mock_write.assert_called_once_with(4, content.encode())
            self.assertEqual(["--file", "3", dest], self.bwrap.args)

    def test_bind_data(self):
        content = "test content"
        dest = "/etc/testfile.conf"
        self.clear_args()
        with patch("os.pipe", return_value=(3, 4)), patch("os.write") as mock_write:
            self.bwrap.bind_data(content, dest)
            mock_write.assert_called_once_with(4, content.encode())
            self.assertEqual(["--ro-bind-data", "3", dest], self.bwrap.args)

    def test_bind_data_home(self):
        content = "test content"
        dest = HOME / "testfile.conf"
        self.clear_args()
        with patch("os.pipe", return_value=(3, 4)), patch("os.write") as mock_write:
            self.bwrap.bind_data(content, dest)
            mock_write.assert_called_once_with(4, content.encode())
            self.assertEqual(
                ["--ro-bind-data", "3", "/home/testuser/testfile.conf"], self.bwrap.args
            )

    def test_bind_data_rw(self):
        content = "test content"
        dest = "/etc/testfile.conf"
        self.clear_args()
        with patch("os.pipe", return_value=(3, 4)), patch("os.write") as mock_write:
            self.bwrap.bind_data(content, dest, mode=BindMode.RW)
            mock_write.assert_called_once_with(4, content.encode())
            self.assertEqual(["--bind-data", "3", dest], self.bwrap.args)

    def test_bind_data_perms(self):
        content = "test content"
        dest = "/etc/testfile.conf"
        self.clear_args()
        with patch("os.pipe", return_value=(3, 4)), patch("os.write") as mock_write:
            self.bwrap.bind_data(content, dest, perms="0775")
            mock_write.assert_called_once_with(4, content.encode())
            self.assertEqual(
                ["--perms", "0775", "--ro-bind-data", "3", dest], self.bwrap.args
            )

    def test_bind_relative_path_to_host_home(self):
        self.clear_args()
        self.bwrap.bind("/src", Path.home() / "dest")
        self.assertEqual(
            ["--ro-bind-try", "/src", str(self.bwrap.home / "dest")], self.bwrap.args
        )

    def test_resolve_path(self):
        home = Path.home()
        resolve_path = self.bwrap.resolve_path
        self.assertEqual(resolve_path(home), self.bwrap.home)
        self.assertEqual(resolve_path(home / "src"), self.bwrap.home / "src")
        self.assertEqual(resolve_path("/src"), Path("/src"))
        self.assertEqual(resolve_path("src"), self.bwrap.cwd / "src")
        self.assertEqual(resolve_path("src", translate=False), Path.cwd() / "src")

    def test_bind_relative_path(self):
        self.clear_args()
        self.bwrap.bind("/src", "dest")
        expected_args = [
            "--ro-bind-try",
            "/src",
            str(self.bwrap.resolve_path(Path.cwd()) / "dest"),
        ]
        self.assertEqual(expected_args, self.bwrap.args)

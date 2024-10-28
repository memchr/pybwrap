import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

from cattr import override


from pybwrap import Bwrap, BindMode
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

    def test_home_bind(self):
        self.clear_args()
        self.bwrap.home_bind(".cache")
        self.assertEqual(
            [
                "--ro-bind-try",
                str(Path.home() / ".cache"),
                str(self.bwrap.home / ".cache"),
            ],
            self.bwrap.args,
        )
        self.clear_args()
        self.bwrap.home_bind(".cache", "device/b", mode=BindMode.DEV)
        self.assertEqual(
            [
                "--dev-bind-try",
                str(Path.home() / ".cache"),
                str(self.bwrap.home / "device/b"),
            ],
            self.bwrap.args,
        )

    # @patch("shutil.copytree")
    # def test_home_copy(self, mock_copytree: MagicMock):
    #     self.bwrap.home_copy("")

    @patch.object(Path, "exists", return_value=True)
    @patch("shutil.copytree")
    def test_home_copy(self, mock_copytree: MagicMock, mock_path_exists: MagicMock):
        src = Path("some/file")
        self.bwrap.home_copy(src, override=True)
        mock_path_exists.assert_called()
        mock_copytree.assert_called_once_with(
            self.bwrap.host_home / src,
            self.bwrap.profile / src,
            dirs_exist_ok=True,
        )

    @patch.object(Path, "exists", return_value=True)
    @patch("shutil.copytree")
    def test_home_copy_dest_contains_host_home(
        self, mock_copytree: MagicMock, mock_path_exists: MagicMock
    ):
        src = Path("some/file")
        dest = Path.home() / "target/path"
        self.bwrap.home_copy(src, dest, override=True)
        mock_path_exists.assert_called()
        mock_copytree.assert_called_once_with(
            self.bwrap.host_home / src,
            self.bwrap.profile / dest.relative_to(Path.home()),
            dirs_exist_ok=True,
        )

    @patch.object(Path, "exists", return_value=True)
    @patch("shutil.copytree")
    def test_home_copy_abs(self, mock_copytree: MagicMock, mock_path_exists: MagicMock):
        src = Path.home() / "path/to/file"
        self.bwrap.home_copy(src, override=True)
        mock_path_exists.assert_called()
        mock_copytree.assert_called_once_with(
            src,
            self.bwrap.profile / src.relative_to(Path.home()),
            dirs_exist_ok=True,
        )

    @patch.object(Path, "exists", return_value=True)
    @patch("shutil.copytree")
    def test_home_copy_abs_outside_host_home(
        self, mock_copytree: MagicMock, mock_path_exists: MagicMock
    ):
        src = Path("/path/to/file")
        dest = Path("target/path")
        self.bwrap.home_copy(src, dest, True)
        mock_copytree.assert_called_once_with(
            src,
            self.bwrap.profile / dest,
            dirs_exist_ok=True,
        )

    @patch.object(Path, "exists", return_value=True)
    @patch("shutil.copytree")
    def test_home_copy_abs_outside_host_home_dest_contains_host_home(
        self, mock_copytree: MagicMock, mock_path_exists: MagicMock
    ):
        src = Path("/path/to/file")
        dest = Path.home() / "target/path"
        self.bwrap.home_copy(src, dest, True)
        mock_copytree.assert_called_once_with(
            src,
            self.bwrap.profile / dest.relative_to(Path.home()),
            dirs_exist_ok=True,
        )

    @patch.object(Path, "exists", return_value=True)
    @patch("shutil.copytree")
    def test_home_copy_abs_outside_host_home_exception(
        self, mock_copytree: MagicMock, mock_path_exists: MagicMock
    ):
        src = Path("/path/to/file")
        self.assertRaises(ValueError, self.bwrap.home_copy, src)
        mock_copytree.assert_not_called()

    def test_home_copy_many(self):
        def mock_copy(bwrap: Bwrap, src: Path, dest: Path = None, override=False):
            logging.debug(f"{bwrap}, {src}, {dest}")
            pass

        with patch.object(Bwrap, "home_copy", mock_copy):
            src = Path("some/file")
            self.bwrap.home_copy_many(
                src,
                override=True,
            )

    @patch.object(Path, "exists", return_value=False)
    @patch("shutil.copytree")
    def test_home_copy_non_existent(self, mock_copytree: MagicMock, *_):
        self.bwrap.home_copy("doesn't exist")
        mock_copytree.assert_not_called()

from pathlib import Path
import unittest

from pybwrap.path import ensure_path


class TestPath(unittest.TestCase):
    def test_ensure_path(self):
        p = ensure_path("/path")
        self.assertEqual(p, Path("/path"))

    def test_ensure_path_2(self):
        p1, p2 = ensure_path("/path/1", Path("/path/2"))
        self.assertEqual(p1, Path("/path/1"))
        self.assertEqual(p2, Path("/path/2"))

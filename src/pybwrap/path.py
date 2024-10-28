from pathlib import Path
from typing import Generator, Union


_PathLike = Union[Path, str]


def _ensure_path_internal(paths):
    for path in paths:
        yield path if isinstance(path, Path) else Path(path)


def ensure_path(*paths: _PathLike) -> Generator[Path, None, None] | Path:
    if len(paths) == 1:
        path = paths[0]
        return path if isinstance(path, Path) else Path(path)
    return _ensure_path_internal(paths)

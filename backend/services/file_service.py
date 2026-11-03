import shutil
from pathlib import Path


def cleanup_files(*paths: str | Path) -> None:
    for path in paths:
        try:
            item = Path(path)
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
        except OSError:
            pass

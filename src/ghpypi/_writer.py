"""Filesystem adapter for rendered Simple Repository indexes."""

from pathlib import Path
from shutil import rmtree

from ._contracts import RenderedIndex


class FilesystemIndexWriter:
    """Replace an output directory with a rendered index."""

    def write(self, index: RenderedIndex, output_dir: Path) -> None:
        """Write *index* beneath *output_dir*."""
        if output_dir.exists():
            rmtree(output_dir)
        for relative_path, contents in index.files.items():
            destination = output_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(contents, encoding="utf-8")

"""Build Simple Repository API pages from GitHub Release snapshots."""

from dataclasses import dataclass
from html import escape
from pathlib import Path, PurePosixPath
from string import hexdigits
from typing import cast
from urllib.parse import unquote, urlsplit, urlunsplit

from packaging.utils import (
    canonicalize_name,
    parse_sdist_filename,
    parse_wheel_filename,
)
from packaging.version import Version

from ._contracts import (
    ArtifactReference,
    GitHubGateway,
    GitHubRelease,
    IndexWriter,
    ReleaseSnapshot,
    ReleaseSnapshots,
    ReleaseTag,
    RenderedIndex,
    RepositoryName,
    SnapshotStore,
)

_SHA256_PREFIX = "sha256:"


@dataclass(frozen=True, slots=True)
class _DistributionFile:
    """A validated distribution file used in a project page."""

    name: str
    project: str
    version: Version
    url: str
    size: int
    sha256: str | None

    @property
    def href(self) -> str:
        """Return the download URL with its available SHA-256 fragment."""
        if self.sha256 is None:
            return self.url
        parts = urlsplit(self.url)
        return urlunsplit(parts._replace(fragment=f"sha256={self.sha256}"))


class IndexRenderer:
    """Render release snapshots as a complete HTML Simple Repository index."""

    def render(self, snapshots: ReleaseSnapshots) -> RenderedIndex:
        """Render and validate the complete index for *snapshots*."""
        projects: dict[str, list[_DistributionFile]] = {}
        for tag in sorted(snapshots.releases):
            for distribution in self._release_files(snapshots.releases[tag]):
                projects.setdefault(distribution.project, []).append(distribution)

        files = {"index.html": self._project_list(projects)}
        files.update(
            {
                f"{project}/index.html": self._project_page(project, distributions)
                for project, distributions in sorted(projects.items())
            }
        )
        return RenderedIndex(files)

    def _release_files(self, snapshot: ReleaseSnapshot) -> list[_DistributionFile]:
        release = snapshot.release
        distributions = [
            self._distribution_file(asset)
            for asset in self._assets(release)
            if self._is_distribution(asset)
        ]
        identities = {
            (distribution.project, distribution.version)
            for distribution in distributions
        }
        if len(identities) > 1:
            msg = "all distribution files in a release must have the same project and version"
            raise ValueError(msg)
        return distributions

    @staticmethod
    def _assets(release: GitHubRelease) -> list[GitHubRelease]:
        assets = release.get("assets", [])
        if not isinstance(assets, list) or not all(
            isinstance(asset, dict) for asset in assets
        ):
            msg = "release assets must be a list of objects"
            raise ValueError(msg)
        return cast("list[GitHubRelease]", assets)

    @staticmethod
    def _is_distribution(asset: GitHubRelease) -> bool:
        name = asset.get("name")
        if not isinstance(name, str):
            msg = "release asset name must be a string"
            raise TypeError(msg)
        return name.endswith((".whl", ".tar.gz"))

    @staticmethod
    def _distribution_file(asset: GitHubRelease) -> _DistributionFile:
        name = cast("str", asset["name"])
        url = asset.get("browser_download_url")
        size = asset.get("size")
        digest = asset.get("digest")
        if (
            not isinstance(url, str)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
        ):
            msg = f"distribution asset has invalid metadata: {name!r}"
            raise ValueError(msg)

        url_parts = urlsplit(url)
        if url_parts.scheme != "https" or url_parts.netloc != "github.com":
            msg = f"distribution asset URL must be an absolute GitHub URL: {name!r}"
            raise ValueError(msg)
        url_name = unquote(PurePosixPath(url_parts.path).name)
        if url_name != name:
            msg = f"distribution URL filename does not match asset name: {name!r}"
            raise ValueError(msg)

        if name.endswith(".whl"):
            project, version, _, _ = parse_wheel_filename(name)
        else:
            project, version = parse_sdist_filename(name)
        project = canonicalize_name(project, validate=True)

        sha256 = None
        if digest is not None:
            if (
                not isinstance(digest, str)
                or not digest.startswith(_SHA256_PREFIX)
                or len(digest) != len(_SHA256_PREFIX) + 64
                or not all(character in hexdigits for character in digest[7:])
            ):
                msg = f"distribution asset has invalid SHA-256 digest: {name!r}"
                raise ValueError(msg)
            sha256 = digest.removeprefix(_SHA256_PREFIX)

        return _DistributionFile(
            name=name,
            project=project,
            version=version,
            url=url,
            size=size,
            sha256=sha256,
        )

    @staticmethod
    def _project_list(
        projects: dict[str, list[_DistributionFile]],
    ) -> str:
        anchors = [
            f'<a href="{escape(project, quote=True)}/">{escape(project)}</a>'
            for project in sorted(projects)
        ]
        return _html_page("Simple index", anchors)

    @staticmethod
    def _project_page(project: str, distributions: list[_DistributionFile]) -> str:
        anchors = [
            f'<a href="{escape(distribution.href, quote=True)}">'
            f"{escape(distribution.name)}</a>"
            for distribution in sorted(
                distributions,
                key=lambda distribution: (distribution.name, distribution.url),
            )
        ]
        return _html_page(f"Links for {project}", anchors)


class PackageIndex:
    """Coordinate repository release-snapshot updates."""

    def __init__(
        self,
        *,
        github: GitHubGateway,
        snapshot_store: SnapshotStore,
        renderer: IndexRenderer,
        writer: IndexWriter,
    ) -> None:
        self._github = github
        self._snapshot_store = snapshot_store
        self._renderer = renderer
        self._writer = writer

    def update(
        self,
        repository: RepositoryName,
        tag: ReleaseTag,
        artifact_ref: ArtifactReference,
        output_dir: Path,
    ) -> None:
        """Update one release snapshot and write the rebuilt index."""
        repository_identity = self._github.get_repository(repository)
        release = self._github.get_release(repository, tag)
        snapshots = self._snapshot_store.load(artifact_ref)
        if snapshots is None:
            snapshots = ReleaseSnapshots.empty(repository_identity)
        else:
            snapshots.verify_repository(repository_identity)

        updated_snapshots = snapshots.replace(tag, release)
        rendered_index = self._renderer.render(updated_snapshots)
        self._snapshot_store.save(artifact_ref, updated_snapshots)
        self._writer.write(rendered_index, output_dir)


def _html_page(title: str, anchors: list[str]) -> str:
    body = "\n".join(f"    {anchor}" for anchor in anchors)
    if body:
        body += "\n"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "  <head>\n"
        '    <meta charset="utf-8">\n'
        '    <meta name="pypi:repository-version" content="1.0">\n'
        f"    <title>{escape(title)}</title>\n"
        "  </head>\n"
        "  <body>\n"
        f"{body}"
        "  </body>\n"
        "</html>\n"
    )

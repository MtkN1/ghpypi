# ghpypi

**PyPI Package Registry for GitHub**

Build a PyPI-compatible package registry with GitHub Releases, GHCR, and GitHub Pages.

ghpypi reads Python distribution assets from a GitHub Release, records them in an OCI catalog stored in GHCR, and generates a static [Simple Repository API][simple-api] under `site/simple/` for publication with GitHub Pages.

[simple-api]: https://packaging.python.org/en/latest/specifications/simple-repository-api/

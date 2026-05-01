# Publishing

VaidCord Python is currently published as a beta package.

Current version: `0.1.0b1`

## Versioning

Use PEP 440 versions in `pyproject.toml`.

Recommended tag formats for Python releases:

- `v0.1.0b1`
- `py-v0.1.0b1`
- `0.1.0b1`

The PyPI workflow validates that the GitHub release tag matches the package
version before publishing.

## PyPI trusted publishing

The workflow `.github/workflows/publish-pypi.yml` uses PyPI trusted publishing
through GitHub Actions OIDC. Do not store PyPI API tokens in the repository.

Configure PyPI with:

- Project name: `vaidcord`
- Owner/repository: `Vadim-Khristenko/vaidcord`
- Workflow name: `publish-pypi.yml`
- Environment: `pypi`

## Release process

1. Update `pyproject.toml` version.
2. Update release notes and docs that mention the current version.
3. Run lint and tests locally.
4. Create a GitHub Release with a matching tag.
5. The publish workflow builds the sdist/wheel and publishes them to PyPI.

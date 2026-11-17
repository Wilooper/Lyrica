# Publishing `lyrica-mcp`

This package is published by the Lyrica project maintainers. A contributor
should not publish it under a personal PyPI account.

## One-time maintainer setup

1. Sign in to the PyPI account that should own `lyrica-mcp`.
2. Add a **pending Trusted Publisher** for:
   - Owner: `Wilooper`
   - Repository: `Lyrica`
   - Workflow: `.github/workflows/publish-mcp.yml`
   - Environment: `pypi`
   - Project name: `lyrica-mcp`
3. In GitHub repository settings, create the `pypi` environment if it does not
   exist. No PyPI API token or GitHub secret is needed.

The pending publisher lets the first successful workflow run create the PyPI
project under the maintainer's account. Once created, PyPI shows the publisher
as a trusted publisher for the project.

## Publish a version

After the release change has been merged into the maintainer-controlled
`feat/mcp-server-v1.5.0` branch:

1. Set `project.version` in `mcp_server/pyproject.toml` to a new, unused
   version. PyPI versions cannot be overwritten or reused.
2. Create and push a matching tag from the release commit, for example:

   ```bash
   git tag lyrica-mcp-v1.5.0
   git push origin lyrica-mcp-v1.5.0
   ```

3. GitHub Actions runs the MCP tests, builds the source distribution and
   wheel, then publishes them to PyPI using Trusted Publishing.

The workflow only runs for tags matching `lyrica-mcp-v*`. The tag version
should match `project.version`; verify the built distribution before tagging.

## Local build / manual upload fallback

From `mcp_server/`, a maintainer with PyPI upload credentials can build and
publish manually:

```bash
uv build
uv publish
```

Provide credentials through `UV_PUBLISH_TOKEN` in the maintainer's shell, not
in source files, command history, or GitHub Actions. Trusted Publishing is the
preferred release path.

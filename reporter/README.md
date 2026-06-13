# AI Fantasy Football Reporter V1

This package is deprecated. The supported reporter is `reporter-v2`, which uses
the single-loop runner and the `reporter_memory` package for persistent
narrative context.

The v1 source remains in the repository as historical reference, but it is no
longer installed as `reporter` or `reporter-v1`, and its tests are not part of
the default pytest suite.

## Supported CLI

```bash
pip install -e .
reporter-v2 "weekly recap" --week 8
```

## Historical Notes

The old v1 `reporter` CLI is no longer installed. Use `reporter-v2` for all
current runs.

Historical design documents remain for reference:

- `docs/design.md` - Reporter agent architecture
- `docs/redesign_iterative_research.md` - Iterative research design

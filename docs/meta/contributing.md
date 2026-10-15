# Contributing

## Development

Install Git and [mise](https://mise.jdx.dev/getting-started.html). On Intel macOS, install Xcode Command Line Tools to build Mr Boxington. Review the repository configuration before approving mise's trust prompt.

Before submitting a change, run these commands from the repository root:

```text
mise run fmt
mise run check
```

Use `mise tasks` to discover individual checks and `mise tasks deps check` to inspect the validation graph. For focused Python work, `mise run test:python -k "navigation or tag"` selects tests, and `mise run lint:python --fix` applies lint fixes. These tasks accept the underlying tool's arguments, including `--help`.

Use `mise run docs:serve` to preview documentation. Keep user guides under `docs/` and project information under `docs/meta/`, and update navigation in `zensical.toml` when adding or moving pages.

## Pull requests

Open pull requests against `main` using the [pull request template](https://github.com/ofek/graftway/blob/main/.github/pull_request_template.md). Contributions follow the [project's licensing terms](https://github.com/ofek/graftway#license).

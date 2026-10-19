# 198x-workflows

The GitHub Actions workflows every 198x family repo shares. A repo calls them instead of carrying its own copy, so a fix lands everywhere at once and the copies can't drift apart.

```yaml
jobs:
  pr-title:
    uses: stevehill1981/198x-workflows/.github/workflows/pr-title.yml@v1
```

## Workflows

| Workflow | What it checks or does |
|---|---|
| [`pr-title.yml`](.github/workflows/pr-title.yml) | Fails a pull request whose title is not a conventional commit, which release-plz needs to bump versions and write changelogs. |

More arrive as the family migrates. The order is set in the umbrella's `docs/plans/2026-10-19-ci-efficiency.md`, part C.

## Versions

Releases are tagged `vX.Y.Z`. The `v1` tag moves to the newest release that callers can take without changes, and callers pin `@v1`. A change that needs callers to change, such as a renamed or removed input, is `v2`.

Keep per-repo behaviour as inputs here, or as a separate local workflow in that repo. Don't copy a shared workflow into a repo: `decisions/project-skeleton-standard.md` in the umbrella records why.

## Licence

GPL-2.0-or-later, like the rest of the family's code.

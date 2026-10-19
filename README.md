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
| [`rust-ci.yml`](.github/workflows/rust-ci.yml) | The universal Rust CI core: format, Clippy, coverage with a floor (also the Linux test run), and a build and test on macOS and Windows. Project jobs stay in the calling `ci.yml`. |
| [`pages-astro.yml`](.github/workflows/pages-astro.yml) | Builds an Astro site and deploys it to GitHub Pages; pull requests build and run the checks without deploying. Inputs for checks before the build and browser checks after it. |
| [`pr-title.yml`](.github/workflows/pr-title.yml) | Fails a pull request whose title or any commit subject is not a conventional commit. release-plz needs them to bump versions and write changelogs, and rebase merging puts every commit on main. |
| [`release-pr.yml`](.github/workflows/release-pr.yml) | Fails a release pull request that sets a manifest version without adding a matching `## [x.y.z]` changelog heading. Other pull requests skip it. |
| [`release-plz.yml`](.github/workflows/release-plz.yml) | Tags merged releases, then opens or updates the next release PR. Inputs cover a pre-tag check, Discord announcements and files to refresh on the release branch. Emu198x keeps its own cut-from-commits release. |

More arrive as the family migrates. The order is set in the umbrella's `docs/plans/2026-10-19-ci-efficiency.md`, part C.

## Versions

Releases are tagged `vX.Y.Z`. The `v1` tag moves to the newest release that callers can take without changes, and callers pin `@v1`. A change that needs callers to change, such as a renamed or removed input, is `v2`.

Keep per-repo behaviour as inputs here, or as a separate local workflow in that repo. Don't copy a shared workflow into a repo: `decisions/project-skeleton-standard.md` in the umbrella records why.

## Licence

GPL-2.0-or-later, like the rest of the family's code.

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
| [`workflow-lint.yml`](.github/workflows/workflow-lint.yml) | Runs actionlint, with pinned shellcheck, on a repository's workflows, honouring its `.github/actionlint.yaml`. `rust-ci.yml` and `pages-astro.yml` include it; other repositories call it directly. |
| [`rust-toolchain.yml`](.github/workflows/rust-toolchain.yml) | Keeps `rust-toolchain.toml` on the latest stable Rust: when stable moves on, opens a `chore: build with Rust <version>` PR so CI checks the new compiler first. Callers run it weekly. |
| [`codeql.yml`](.github/workflows/codeql.yml) | CodeQL code scanning, one job per language from a `languages` input. Callers run it on pushes to `main`, weekly and by hand. |
| [`discord-release.yml`](.github/workflows/discord-release.yml) | Announces a cargo-dist GitHub Release in Discord, called from a repo's `notify-discord.yml` post-announce job. Full notes go to the project channel, and a one-line digest linking to them to the family channel. |

More arrive as the family migrates. The order is set in the umbrella's `docs/plans/2026-10-19-ci-efficiency.md`, part C.

## Scripts

`scripts/discord_announce.py` does the posting for both Discord workflows, and `scripts/rust_toolchain.py` decides when a Rust pin needs bumping. Their tests run with `python3 -m unittest discover scripts`.

## Versions

This repository's own CI (`ci.yml`) runs the script tests, lints every workflow here with `workflow-lint.yml`, and checks PR titles. `main` accepts only pull requests that pass it. Move `v1` only to a commit whose CI passed on `main`, because moving it changes every family repository at once.

Releases are tagged `vX.Y.Z`. The `v1` tag moves to the newest release that callers can take without changes, and callers pin `@v1`. A change that needs callers to change, such as a renamed or removed input, is `v2`.

Keep per-repo behaviour as inputs here, or as a separate local workflow in that repo. Don't copy a shared workflow into a repo: `decisions/project-skeleton-standard.md` in the umbrella records why.

## Licence

GPL-2.0-or-later, like the rest of the family's code.

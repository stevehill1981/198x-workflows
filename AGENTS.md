# 198x-workflows

Reusable GitHub Actions workflows (`on: workflow_call`) shared by every 198x family repo. The binding rule is the umbrella's `decisions/project-skeleton-standard.md`. The migration plan is `docs/plans/2026-10-19-ci-efficiency.md`, part C.

- Every job has `timeout-minutes`. Every action is pinned to a major version.
- Concurrency belongs to the calling workflow, not here.
- Per-repo behaviour is an input with a default that keeps existing callers unchanged.
- Changing what an input means, or removing one, is a new major version (`v2`), not a change to `v1`.
- To release, tag `vX.Y.Z`, then move `v1` to it: `git tag -f v1 vX.Y.Z && git push -f origin v1`. The `v1` tag is the one moving ref; never move a `vX.Y.Z` tag.
- Test a change on a pilot repo by pointing its caller at the branch (`@my-branch`) before tagging.

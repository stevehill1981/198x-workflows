# Compile existing host dependencies during release checks

ColecoVision's merged runtime save fix cannot prepare a release: cargo-semver-checks
builds emu198x-shell and fails in libudev-sys/alsa-sys because the Linux headers
are absent. Its ordinary CI already declares pkg-config, libasound2-dev and
libudev-dev. No crate dependency or semver gate needs changing.

1. Add optional linux-packages to release-plz.yml with the same empty default
   and bounded apt/mirror setup used by rust-ci.yml, before both release commands.
2. Run actionlint and all existing script tests; push through normal PR CI.
3. Pilot ColecoVision's caller against the task branch, declaring its existing
   Linux prerequisites. Verify the actual release-pr job builds rustdoc and
   prepares the runtime release. Keep semver checks enabled.
4. Once shared main and the pilot pass, publish a new immutable patch tag and
   move only the documented v1 alias. Restore the caller to v1 before finishing.
5. Publish the corrected runtime through its reviewed release PR, then update
   the umbrella's registry dependency. Retain evidence and clean the task
   worktree. Shared worktree: /private/tmp/198x-release-linux-packages.

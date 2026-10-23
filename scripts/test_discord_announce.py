"""Tests for discord_announce.py. Run with: python3 -m unittest discover scripts"""

import tempfile
import unittest
from pathlib import Path

import discord_announce as da

# The shape of an Emu198x release body: a few notes, then one install and
# download section per binary.
EMU_BODY = """## Release Notes

### Fixed

- Stop Amiga run-to-address and breakpoints missing their target
- Make the 68000 trap ILLEGAL instead of running it as TAS

# emu198x-acorn-atom 0.44.1

## Install emu198x-acorn-atom 0.44.1

```sh
brew install emu198x/tap/emu198x-acorn-atom
```

## Download emu198x-acorn-atom 0.44.1

| File | Platform | Checksum |
"""

# The shape of an asm198x release body: notes, then installers.
ASM_BODY = """## Release Notes

### Fixed

- SjASMPlus shifts now use signed 32-bit operands. ([#727](https://example.test/727))

### Added

- SjASMPlus writes NEX files.

## Install asm198x 0.0.71

### Install prebuilt binaries via shell script
"""


class FakeDiscord:
    """Records requests and answers like Discord's webhook API."""

    def __init__(self, fail_on=(), guild_in_message=False):
        self.requests = []
        self.fail_on = fail_on
        self.guild_in_message = guild_in_message
        self.next_id = 100

    def __call__(self, method, url, body):
        self.requests.append((method, url, body))
        if any(marker in url for marker in self.fail_on) and method == "POST":
            raise RuntimeError("Discord answered 400")
        if method == "GET":
            return {"guild_id": "G1"}
        if url.endswith("?wait=true"):
            self.next_id += 1
            message = {"id": str(self.next_id), "channel_id": "C1"}
            if self.guild_in_message:
                message["guild_id"] = "G9"
            return message
        return None

    def posts_to(self, marker):
        return [body for method, url, body in self.requests if method == "POST" and marker in url]


PROJECT = "https://discord.com/api/webhooks/1/project"
FAMILY = "https://discord.com/api/webhooks/2/family"


def item(title="emu198x v0.44.1", notes=None):
    return da.Announcement(
        title=title,
        url="https://github.com/emu198x/emu198x/releases/tag/v0.44.1",
        notes=da.release_notes(EMU_BODY) if notes is None else notes,
        repo="emu198x/emu198x",
        links=["[download and install](https://github.com/emu198x/emu198x/releases/tag/v0.44.1)"],
    )


class ReleaseNotesTest(unittest.TestCase):
    def test_drops_per_binary_install_sections(self):
        notes = da.release_notes(EMU_BODY)
        self.assertTrue(notes.startswith("### Fixed"))
        self.assertIn("TAS", notes)
        self.assertNotIn("acorn-atom", notes)
        self.assertNotIn("brew", notes)

    def test_drops_installers_but_keeps_every_notes_section(self):
        notes = da.release_notes(ASM_BODY)
        self.assertIn("### Added", notes)
        self.assertNotIn("Install", notes)

    def test_a_body_without_install_sections_is_kept(self):
        self.assertEqual(da.release_notes("### Fixed\n\n- One thing\n"), "### Fixed\n\n- One thing")

    def test_an_empty_body_gives_empty_notes(self):
        self.assertEqual(da.release_notes(""), "")


class ReleaseTitleTest(unittest.TestCase):
    def test_names_the_project_when_cargo_dist_leaves_it_out(self):
        self.assertEqual(
            da.release_title("0.44.1 - 2026-10-22", "v0.44.1", "emu198x/emu198x"),
            "emu198x 0.44.1 - 2026-10-22",
        )

    def test_keeps_a_title_that_already_names_the_project(self):
        self.assertEqual(
            da.release_title("build198x-adf 0.2.13", "build198x-adf-v0.2.13", "build198x/build198x"),
            "build198x-adf 0.2.13",
        )

    def test_falls_back_to_the_tag(self):
        self.assertEqual(da.release_title("", "v1.0.0", "emu198x/emu198x"), "emu198x v1.0.0")


class ChangelogSectionTest(unittest.TestCase):
    def test_does_not_match_a_longer_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CHANGELOG.md"
            path.write_text("## [0.1.10] - d\n\n- ten\n\n## [0.1.1] - d\n\n- one\n")
            self.assertEqual(da.changelog_section(path, "0.1.1"), "- one")
            self.assertEqual(da.changelog_section(path, "0.1.10"), "- ten")

    def test_missing_file_or_version_gives_empty(self):
        self.assertEqual(da.changelog_section(Path("/nonexistent/CHANGELOG.md"), "1.0.0"), "")


class SummaryTest(unittest.TestCase):
    def test_counts_bullets_per_section(self):
        self.assertEqual(da.change_counts(da.release_notes(ASM_BODY)), "1 fixed, 1 added")

    def test_prose_without_sections_has_no_counts(self):
        self.assertEqual(da.change_counts("The first release."), "")

    def test_long_notes_are_truncated_with_a_link(self):
        cut = da.truncate("x" * (da.NOTES_LIMIT + 50), "https://example.test")
        self.assertTrue(cut.endswith("[Full notes](https://example.test)"))
        self.assertLess(len(cut), da.NOTES_LIMIT + 100)


class AnnounceTest(unittest.TestCase):
    def test_family_digest_links_to_the_project_message(self):
        discord = FakeDiscord()
        self.assertEqual(da.announce([item()], PROJECT, FAMILY, discord), 0)
        # The project post comes first and waits for its message.
        method, url, body = discord.requests[0]
        self.assertEqual((method, url), ("POST", PROJECT + "?wait=true"))
        self.assertNotIn("brew", body["embeds"][0]["description"])
        digest = discord.posts_to("family")[0]["content"]
        self.assertIn("https://discord.com/channels/G1/C1/101", digest)
        self.assertIn("2 fixed", digest)
        self.assertNotIn("embeds", discord.posts_to("family")[0])

    def test_uses_the_guild_from_the_message_when_present(self):
        discord = FakeDiscord(guild_in_message=True)
        da.announce([item()], PROJECT, FAMILY, discord)
        self.assertIn("channels/G9/C1/", discord.posts_to("family")[0]["content"])
        self.assertFalse([r for r in discord.requests if r[0] == "GET"])

    def test_digest_falls_back_to_the_release_when_the_project_post_fails(self):
        discord = FakeDiscord(fail_on=("project",))
        self.assertEqual(da.announce([item()], PROJECT, FAMILY, discord), 1)
        digest = discord.posts_to("family")[0]["content"]
        self.assertIn("[release](<https://github.com/emu198x/emu198x/releases/tag/v0.44.1>)", digest)

    def test_without_a_project_channel_the_digest_links_to_the_release(self):
        discord = FakeDiscord()
        da.announce([item()], "", FAMILY, discord)
        self.assertEqual(len(discord.requests), 1)
        self.assertIn("[release](<", discord.posts_to("family")[0]["content"])

    def test_without_a_family_channel_the_project_post_does_not_wait(self):
        discord = FakeDiscord()
        da.announce([item()], PROJECT, "", discord)
        self.assertEqual(discord.requests, [("POST", PROJECT, da.full_payload(item()))])

    def test_one_channel_named_twice_gets_the_full_post_only(self):
        discord = FakeDiscord()
        da.announce([item()], PROJECT, PROJECT, discord)
        self.assertEqual(len(discord.requests), 1)
        self.assertIn("embeds", discord.requests[0][2])

    def test_no_webhooks_posts_nothing(self):
        discord = FakeDiscord()
        self.assertEqual(da.announce([item()], "", "", discord), 0)
        self.assertEqual(discord.requests, [])

    def test_several_releases_share_one_digest_message(self):
        discord = FakeDiscord()
        da.announce([item("a v1"), item("b v2")], PROJECT, FAMILY, discord)
        self.assertEqual(len(discord.posts_to("project")), 2)
        digests = discord.posts_to("family")
        self.assertEqual(len(digests), 1)
        self.assertEqual(digests[0]["content"].count("\n"), 1)

    def test_a_failed_digest_is_counted(self):
        discord = FakeDiscord(fail_on=("family",))
        self.assertEqual(da.announce([item()], PROJECT, FAMILY, discord), 1)

    def test_mentions_are_never_parsed(self):
        discord = FakeDiscord()
        da.announce([item(notes="### Fixed\n\n- ping @everyone")], PROJECT, FAMILY, discord)
        for _, _, body in discord.requests:
            if body:
                self.assertEqual(body["allowed_mentions"], {"parse": []})


class DigestPackingTest(unittest.TestCase):
    def test_long_digests_split_under_the_content_limit(self):
        lines = ["x" * 900] * 5
        payloads = da.digest_payloads(lines)
        self.assertGreater(len(payloads), 1)
        for payload in payloads:
            self.assertLessEqual(len(payload["content"]), da.CONTENT_LIMIT)
        self.assertEqual(sum(p["content"].count("x") for p in payloads), 4500)


class ReleasePlzSourceTest(unittest.TestCase):
    def test_skips_packages_announced_by_their_binary_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            releases = [
                {"package_name": "build198x", "version": "0.2.13", "tag": "build198x-v0.2.13"},
                {"package_name": "mediaspec198x", "version": "0.1.0", "tag": "mediaspec198x-v0.1.0"},
            ]
            items = da.from_release_plz(
                releases, "build198x/build198x", "https://github.com", Path(tmp),
                {"build198x"}, published=lambda p, v: True,
            )
        self.assertEqual([i.title for i in items], ["mediaspec198x v0.1.0"])
        self.assertIn("[docs.rs](https://docs.rs/mediaspec198x/0.1.0)", items[0].links)

    def test_finds_a_crate_whose_folder_is_not_its_package_name(self):
        # lang198x-syntax lives in crates/syntax.
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "aaa"
            other.mkdir()
            (other / "Cargo.toml").write_text('[package]\nname = "something-else"\n')
            broken = Path(tmp) / "broken"
            broken.mkdir()
            (broken / "Cargo.toml").write_text("[package\n")
            crate = Path(tmp) / "syntax"
            crate.mkdir()
            (crate / "Cargo.toml").write_text('[package]\nname = "lang198x-syntax"\nversion = "0.1.2"\n')
            (crate / "CHANGELOG.md").write_text("## [0.1.2] - d\n\nProvenance arrives.\n")
            items = da.from_release_plz(
                [{"package_name": "lang198x-syntax", "version": "0.1.2", "tag": ""}],
                "lang198x/syntax", "https://github.com", Path(tmp), set(),
                published=lambda p, v: True,
            )
            missing = da.crate_changelog(Path(tmp), "not-a-crate")
        self.assertEqual(items[0].notes, "Provenance arrives.")
        self.assertEqual(missing, Path(tmp) / "not-a-crate" / "CHANGELOG.md")

    def test_reads_notes_from_the_crate_changelog(self):
        with tempfile.TemporaryDirectory() as tmp:
            crate = Path(tmp) / "lang198x-syntax"
            crate.mkdir()
            (crate / "CHANGELOG.md").write_text("## [0.2.0] - d\n\n### Added\n\n- The tree.\n")
            items = da.from_release_plz(
                [{"package_name": "lang198x-syntax", "version": "0.2.0", "tag": ""}],
                "lang198x/syntax", "https://github.com", Path(tmp), set(),
                published=lambda p, v: True,
            )
        self.assertEqual(items[0].notes, "### Added\n\n- The tree.")
        self.assertEqual(items[0].url, "https://crates.io/crates/lang198x-syntax/0.2.0")


if __name__ == "__main__":
    unittest.main()

"""Tests for rust_toolchain.py. Run with: python3 -m unittest discover scripts"""

import unittest

import rust_toolchain as rt

MANIFEST = """manifest-version = "2"
date = "2026-10-13"

[pkg.cargo]
version = "0.100.1 (5f94df478 2026-08-27)"

[pkg.rust]
version = "1.99.1 (58cf8f9c3 2026-10-13)"
"""

PIN = """[toolchain]
channel = "1.98.0"
components = ["clippy", "rustfmt"]
"""


class ToolchainTest(unittest.TestCase):
    def test_reads_rust_not_cargo_from_the_manifest(self):
        self.assertEqual(rt.latest_stable(MANIFEST), "1.99.1")

    def test_reads_the_pinned_channel(self):
        self.assertEqual(rt.pinned(PIN), "1.98.0")
        self.assertIsNone(rt.pinned("[toolchain]\ncomponents = []\n"))

    def test_bumps_only_an_older_version(self):
        self.assertTrue(rt.needs_bump("1.98.0", "1.99.1"))
        self.assertTrue(rt.needs_bump("1.99.0", "1.99.1"))
        self.assertFalse(rt.needs_bump("1.99.1", "1.99.1"))
        self.assertFalse(rt.needs_bump("1.100.0", "1.99.1"))

    def test_compares_numerically_not_as_text(self):
        self.assertTrue(rt.needs_bump("1.9.0", "1.10.0"))

    def test_leaves_deliberate_channels_alone(self):
        self.assertFalse(rt.needs_bump("stable", "1.99.1"))
        self.assertFalse(rt.needs_bump("nightly-2026-09-24", "1.99.1"))
        self.assertFalse(rt.needs_bump(None, "1.99.1"))

    def test_rewrites_only_the_channel(self):
        self.assertEqual(
            rt.bumped(PIN, "1.99.1"),
            '[toolchain]\nchannel = "1.99.1"\ncomponents = ["clippy", "rustfmt"]\n',
        )

    def test_keeps_comments_and_spacing(self):
        text = '# pinned for the family\n[toolchain]\n  channel  =  "1.98.0" # bumped weekly\n'
        self.assertEqual(
            rt.bumped(text, "1.99.1"),
            '# pinned for the family\n[toolchain]\n  channel  =  "1.99.1" # bumped weekly\n',
        )


if __name__ == "__main__":
    unittest.main()

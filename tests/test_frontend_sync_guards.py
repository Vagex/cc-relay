import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "codex_web_relay.py"


class FrontendSyncGuardsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_profile_persistence_watcher_does_not_sync_every_edit(self):
        match = re.search(
            r"watch\(\[profiles, activeProfileId, settings\], \(\) => \{(?P<body>.*?)\}, \{ deep: true \}\);",
            self.source,
            re.S,
        )
        self.assertIsNotNone(match, "profile/settings persistence watcher should exist")
        self.assertIn("persistProfiles();", match.group("body"))
        self.assertNotIn("sync();", match.group("body"))

    def test_active_profile_has_separate_sync_watcher(self):
        self.assertIn("const activeSyncPayload = computed", self.source)
        self.assertRegex(self.source, r"watch\(activeSyncPayload,\s*\(\) => \{\s*sync\(\);")


if __name__ == "__main__":
    unittest.main()

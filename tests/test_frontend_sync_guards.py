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

    def test_enabling_profile_waits_for_sync(self):
        self.assertIn("const sync = async (profile = activeProfile.value)", self.source)
        self.assertIn("const stateRes = await fetch('/relay/v1/internal/state');", self.source)
        self.assertIn("if (!matches) throw new Error", self.source)
        self.assertIn("const enableProfile = async (id) =>", self.source)
        self.assertIn("const synced = await sync(target);", self.source)
        self.assertIn("if (!synced) return;", self.source)
        self.assertIn("const enableSelectedProfile = async () =>", self.source)

    def test_saving_active_profile_waits_for_sync(self):
        self.assertIn("const saveAndExit = async () =>", self.source)
        self.assertIn("selectedProfile.value?.id === activeProfileId.value", self.source)
        self.assertIn("await sync(selectedProfile.value);", self.source)

    def test_web_chat_syncs_active_snapshot_before_send(self):
        self.assertIn("const profile = activeProfile.value;", self.source)
        self.assertIn("const synced = await sync(profile);", self.source)
        self.assertIn("if (!synced) throw new Error(t('syncFailed'));", self.source)
        self.assertIn("...upstreamHeaders(profile, cleanKey)", self.source)

    def test_chat_history_resets_when_model_changes(self):
        self.assertIn("const chatProfileFingerprint = (profile) => JSON.stringify", self.source)
        self.assertIn("const previousChatProfile = chatProfileFingerprint(activeProfile.value);", self.source)
        self.assertIn("if (previousChatProfile !== chatProfileFingerprint(target))", self.source)
        self.assertIn("chatHistory.value = [];", self.source)
        self.assertIn("chatResetForModel", self.source)

    def test_user_chat_bubble_is_plain(self):
        self.assertIn("terminalUser: '終端指令'", self.source)
        self.assertIn("terminalUser: 'User input'", self.source)
        self.assertIn("self-end bg-white/80 text-slate-800 p-4 rounded-xl", self.source)
        self.assertNotIn("msg.role === 'user' ? 'prose-invert text-white'", self.source)

    def test_local_ollama_hosts_do_not_require_api_keys(self):
        self.assertIn("'127.0.0.1'", self.source)
        self.assertIn("'host.docker.internal'", self.source)
        self.assertIn("new URL(profile?.baseUrl || '').hostname", self.source)

    def test_legacy_preset_names_are_treated_as_generated_names(self):
        self.assertIn("const legacyPresetNames = [", self.source)
        self.assertIn("'本地 Ollama'", self.source)
        self.assertIn("'Ollama Docker Desktop'", self.source)
        self.assertIn("...legacyPresetNames", self.source)
        self.assertIn("...Object.values(presets).flatMap", self.source)
        self.assertIn("translations['zh-TW'][preset.nameKey]", self.source)
        self.assertIn("translations.en[preset.nameKey]", self.source)


if __name__ == "__main__":
    unittest.main()

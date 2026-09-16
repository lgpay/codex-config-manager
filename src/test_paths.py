# -*- coding: utf-8 -*-
"""配置路径设置、解析、探测与热切换测试；所有写入均在临时目录。"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import core


class PathSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="path_settings_")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.profile = self.base / "profile"
        self.local = self.base / "local"
        self.roaming = self.base / "roaming"
        self.profile.mkdir()
        self.local.mkdir()
        self.roaming.mkdir()
        self.settings = self.base / "manager" / "settings.json"
        self.env = patch.dict(os.environ, {
            "USERPROFILE": str(self.profile),
            "LOCALAPPDATA": str(self.local),
            "APPDATA": str(self.roaming),
            core.SETTINGS_ENV: str(self.settings),
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def make_home(self, name="home", config=True, presets=1):
        home = self.base / name
        configs = home / "configs"
        configs.mkdir(parents=True)
        if config:
            (home / "config.toml").write_text('model = "x"\n', encoding="utf-8")
        for i in range(presets):
            (configs / f"p{i}.toml").write_text('model = "x"\n', encoding="utf-8")
        return home

    def test_settings_missing_and_default_location(self):
        result = core.load_settings()
        self.assertEqual(result["status"], "missing")
        self.assertEqual(Path(result["path"]), self.settings.resolve())
        self.assertFalse(self.settings.exists())

    def test_save_load_utf8_atomic_and_strict_types(self):
        home = self.make_home("中文目录")
        library = self.base / "预设库"
        saved = core.save_settings(home, library)
        self.assertEqual(saved["schema_version"], 1)
        raw = self.settings.read_bytes()
        self.assertIn("中文目录".encode("utf-8"), raw)
        self.assertFalse(any(x.name.startswith(".__tmp_") for x in self.settings.parent.iterdir()))
        loaded = core.load_settings()
        self.assertTrue(loaded["ok"])
        self.assertEqual(Path(loaded["settings"]["codex_home"]), home.resolve())
        self.settings.write_text(json.dumps({"schema_version": True, "codex_home": str(home),
                                             "configs_dir": str(library)}), encoding="utf-8")
        bad = core.load_settings()
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["status"], "corrupt")

    def test_corrupt_settings_recover_without_crash(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("{broken", encoding="utf-8")
        paths, resolved = core.Paths.for_gui()
        self.assertEqual(paths.root, (self.profile / ".codex").resolve())
        self.assertEqual(resolved["settings"]["status"], "corrupt")
        home = self.make_home("recovered")
        core.save_settings(home, home / "custom-presets")
        self.assertEqual(core.load_settings()["status"], "ok")

    def test_priority_explicit_environment_settings_default(self):
        setting_home = self.make_home("setting")
        core.save_settings(setting_home, self.base / "setting-library")
        resolved = core.resolve_paths()
        self.assertEqual(resolved["source"], "settings")
        self.assertEqual(resolved["root"], setting_home.resolve())
        env_home = self.make_home("env")
        with patch.dict(os.environ, {"CODEX_HOME": str(env_home)}):
            env_resolved = core.resolve_paths()
            self.assertEqual(env_resolved["source"], "environment")
            self.assertEqual(env_resolved["configs_dir"], (env_home / "configs").resolve())
            explicit_lib = self.base / "explicit-library"
            explicit = core.resolve_paths(explicit_root=self.base / "explicit-home",
                                          explicit_configs=explicit_lib)
            self.assertEqual(explicit["source"], "explicit")
            self.assertEqual(explicit["configs_source"], "explicit")
            self.assertEqual(explicit["configs_dir"], explicit_lib.resolve())
        self.settings.unlink()
        fallback = core.resolve_paths()
        self.assertEqual(fallback["source"], "default")
        self.assertEqual(fallback["root"], (self.profile / ".codex").resolve())

    def test_paths_custom_library_keeps_history_with_library(self):
        home = self.make_home("root", presets=0)
        library = self.base / "elsewhere" / "presets"
        paths = core.Paths(home, library)
        self.assertEqual(paths.live, home / "config.toml")
        self.assertEqual(paths.lib, library.resolve())
        self.assertEqual(paths.history, library.resolve() / ".history")
        core.ensure_layout(paths)
        self.assertTrue(library.is_dir())

    def test_validation_rejects_file_relative_and_config_file_home(self):
        file_path = self.base / "not-directory"
        file_path.write_text("x", encoding="utf-8")
        with self.assertRaises(core.CoreError):
            core.normalize_configs_dir(file_path)
        with self.assertRaises(core.CoreError):
            core.normalize_codex_home(self.base / "config.toml")
        with self.assertRaises(core.CoreError):
            core.normalize_codex_home("relative/path")

    def test_probe_is_limited_deduplicated_and_never_reads_config_contents(self):
        default = self.profile / ".codex"
        (default / "configs").mkdir(parents=True)
        (default / "config.toml").write_text('api_key = "must-not-leak"\n', encoding="utf-8")
        (default / "configs" / "a.toml").write_text("x=1\n", encoding="utf-8")
        known = self.local / "OpenAI" / "Codex"
        (known / "configs").mkdir(parents=True)
        (known / "configs" / "b.toml").write_text("x=1\n", encoding="utf-8")
        with patch.dict(os.environ, {"CODEX_HOME": str(default)}):
            rows = core.probe_codex_locations()
        paths = [Path(x["path"]) for x in rows]
        self.assertEqual(len(paths), len({os.path.normcase(str(x)) for x in paths}))
        self.assertIn(default.resolve(), paths)
        self.assertIn(known.resolve(), paths)
        public = json.dumps(rows, ensure_ascii=False)
        self.assertNotIn("must-not-leak", public)
        self.assertEqual(next(x for x in rows if Path(x["path"]) == default.resolve())["preset_count"], 1)

    def test_api_save_before_switch_and_environment_lock(self):
        old = self.make_home("old")
        new = self.base / "new-home"
        new_lib = self.base / "new-library"
        original = core.Paths(old)
        context = {"source": "default", "configs_source": "default",
                   "env_controlled": False, "settings": core.load_settings()}
        api = app.Api(original, path_context=context, settings_file=self.settings)
        refused_missing = api.apply_paths(str(new), str(new_lib), create=False)
        self.assertFalse(refused_missing["ok"])
        self.assertIs(api.p, original)
        result = api.apply_paths(str(new), str(new_lib), create=True)
        self.assertTrue(result["ok"], result)
        self.assertEqual(api.p.root, new.resolve())
        self.assertEqual(api.p.lib, new_lib.resolve())
        self.assertTrue(new.is_dir())
        self.assertTrue(new_lib.is_dir())
        self.assertEqual(Path(core.load_settings()["settings"]["configs_dir"]), new_lib.resolve())
        locked = app.Api(original, path_context={"env_controlled": True,
                         "settings": core.load_settings()}, settings_file=self.settings)
        refused = locked.apply_paths(str(new), str(new_lib))
        self.assertFalse(refused["ok"])
        self.assertTrue(refused["env_controlled"])
        self.assertEqual(locked.p.root, old.resolve())

    def test_api_save_failure_does_not_switch_memory(self):
        old = self.make_home("old-fail")
        api = app.Api(core.Paths(old), path_context={"env_controlled": False,
                      "settings": core.load_settings()}, settings_file=self.settings)
        before = api.p
        with patch("core.save_settings", side_effect=OSError("denied")):
            result = api.apply_paths(str(self.base / "next"), str(self.base / "next-lib"), create=True)
        self.assertFalse(result["ok"])
        self.assertIs(api.p, before)

    def test_initial_auto_adopts_only_valid_default(self):
        default = self.profile / ".codex"
        (default / "configs").mkdir(parents=True)
        (default / "config.toml").write_text("x=1\n", encoding="utf-8")
        paths, context = core.Paths.for_gui()
        api = app.Api(paths, path_context=context, settings_file=self.settings)
        initial = api.initial()
        self.assertFalse(initial["path_setup"])
        self.assertTrue(initial["path_auto_saved"])
        self.assertEqual(core.load_settings()["status"], "ok")


if __name__ == "__main__":
    unittest.main(verbosity=2)

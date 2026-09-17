# -*- coding: utf-8 -*-
"""启动 ChatGPT：只验证入口发现与启动调用，不真的启动任何应用。

所有用例都用**注入的应用列表**，不查询真实系统、不调用 explorer.exe；
唯一涉及系统的一处（subprocess）也被 patch 掉。
"""

# --- 输出编码：CI（windows-latest）控制台默认 cp1252，中文断言名会 UnicodeEncodeError ---
import sys as _sys_enc
try:
    _sys_enc.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_enc.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import subprocess
import unittest
from unittest.mock import patch

import launcher

CHATGPT = {"name": "ChatGPT", "id": "OpenAI.Sample_abc123!App"}


def entry(name, app_id):
    return {"name": name, "id": app_id}


class TestFindChatgpt(unittest.TestCase):
    def test_exact_name_match(self):
        r = launcher.find_chatgpt([entry("ChatGPT", "OpenAI.Sample_abc!App")])
        self.assertTrue(r["ok"])
        self.assertEqual(r["entry"]["id"], "OpenAI.Sample_abc!App")
        self.assertEqual(r["matched"], "name_exact")

    def test_exact_match_is_case_insensitive_and_trimmed(self):
        r = launcher.find_chatgpt([entry("  chatgpt  ", "A.B_c!App")])
        self.assertTrue(r["ok"])
        self.assertEqual(r["entry"]["id"], "A.B_c!App")

    def test_exact_match_wins_over_prefix(self):
        r = launcher.find_chatgpt([
            entry("ChatGPT Classic", "A.B_c!Old"),
            entry("ChatGPT", "A.B_c!New"),
        ])
        self.assertTrue(r["ok"])
        self.assertEqual(r["entry"]["id"], "A.B_c!New")
        self.assertEqual(r["matched"], "name_exact")

    def test_single_prefix_candidate_is_accepted(self):
        r = launcher.find_chatgpt([entry("ChatGPT (Beta)", "A.B_c!Beta")])
        self.assertTrue(r["ok"])
        self.assertEqual(r["matched"], "name_prefix")

    def test_multiple_prefix_candidates_rejected(self):
        r = launcher.find_chatgpt([
            entry("ChatGPT A", "A.B_c!A"),
            entry("ChatGPT B", "A.B_c!B"),
        ])
        self.assertFalse(r["ok"])
        self.assertIn("多个", r["error"])
        self.assertEqual(len(r["candidates"]), 2)

    def test_codex_entry_is_not_treated_as_chatgpt(self):
        """Codex 与 ChatGPT 同包但显示名不同，不得自动冒充。"""
        r = launcher.find_chatgpt([
            entry("Codex", "OpenAI.Codex_abc!App"),
            entry("Codex 配置管理器", r"C:\Users\x\bin\CodexConfigManager.exe"),
        ])
        self.assertFalse(r["ok"])
        self.assertEqual(r["candidates"], [])

    def test_empty_list_reports_missing(self):
        r = launcher.find_chatgpt([])
        self.assertFalse(r["ok"])
        self.assertIn("未检测到", r["error"])

    def test_unlaunchable_ids_are_skipped(self):
        bad = [entry("ChatGPT", "A.B_c!App\nwhoami"), entry("ChatGPT", "'quoted"),
               entry("ChatGPT", "")]
        r = launcher.find_chatgpt(bad)
        self.assertFalse(r["ok"])

    def test_overlong_id_is_skipped(self):
        r = launcher.find_chatgpt([entry("ChatGPT", "A" * 400)])
        self.assertFalse(r["ok"])

    def test_real_world_entry_shape(self):
        """本机实测形态：桌面 ChatGPT 来自 OpenAI.Codex 包族名。"""
        r = launcher.find_chatgpt([entry("ChatGPT", "OpenAI.Codex_2p2nqsd0c76g0!App")])
        self.assertTrue(r["ok"])
        self.assertEqual(r["entry"]["id"], "OpenAI.Codex_2p2nqsd0c76g0!App")


class TestListStartApps(unittest.TestCase):
    def test_parses_json_array(self):
        payload = b'[{"name":"ChatGPT","id":"A.B_c!App"},{"name":"Other","id":"X.Y_z"}]'
        with patch.object(launcher.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, payload, b"")):
            items = launcher.list_start_apps()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["name"], "ChatGPT")

    def test_single_object_is_wrapped(self):
        payload = b'{"name":"ChatGPT","id":"A.B_c!App"}'
        with patch.object(launcher.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, payload, b"")):
            items = launcher.list_start_apps()
        self.assertEqual(len(items), 1)

    def test_invalid_json_returns_empty(self):
        with patch.object(launcher.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, b"not json", b"")):
            self.assertEqual(launcher.list_start_apps(), [])

    def test_nonzero_exit_returns_empty(self):
        with patch.object(launcher.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 1, b"", b"err")):
            self.assertEqual(launcher.list_start_apps(), [])

    def test_timeout_returns_empty_without_raising(self):
        with patch.object(launcher.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("powershell", 12)):
            self.assertEqual(launcher.list_start_apps(), [])

    def test_missing_powershell_is_not_fatal(self):
        with patch.object(launcher.subprocess, "run", side_effect=OSError("missing")):
            self.assertEqual(launcher.list_start_apps(), [])

    def test_dev_garbage_output_returns_empty(self):
        with patch.object(launcher.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, b"[1, 2, 3]", b"")):
            self.assertEqual(launcher.list_start_apps(), [])


class TestLaunch(unittest.TestCase):
    def test_launch_uses_apps_folder_and_no_shell(self):
        seen = {}

        def fake_popen(argv, **kw):
            seen["argv"] = argv
            seen["kw"] = kw
            return object()

        with patch.object(launcher.subprocess, "Popen", side_effect=fake_popen):
            r = launcher.launch("OpenAI.Sample_abc!App")
        self.assertTrue(r["ok"])
        self.assertEqual(r["method"], "shell:AppsFolder")
        self.assertEqual(seen["argv"][0], "explorer.exe")
        self.assertEqual(seen["argv"][1], "shell:AppsFolder\\OpenAI.Sample_abc!App")
        self.assertNotIn("shell", seen["kw"])

    def test_invalid_id_rejected_before_system_call(self):
        with patch.object(launcher.subprocess, "Popen") as p:
            r = launcher.launch("../evil")
        self.assertFalse(r["ok"])
        p.assert_not_called()

    def test_blank_id_rejected(self):
        with patch.object(launcher.subprocess, "Popen") as p:
            r = launcher.launch("   ")
        self.assertFalse(r["ok"])
        p.assert_not_called()

    def test_popen_oserror_reports_failure(self):
        with patch.object(launcher.subprocess, "Popen", side_effect=OSError("denied")):
            r = launcher.launch("OpenAI.Sample_abc!App")
        self.assertFalse(r["ok"])


class TestLaunchChatgpt(unittest.TestCase):
    def test_success_path_returns_message(self):
        with patch.object(launcher.subprocess, "Popen", return_value=object()):
            r = launcher.launch_chatgpt([entry("ChatGPT", "OpenAI.Sample_abc!App")])
        self.assertTrue(r["ok"])
        self.assertEqual(r["name"], "ChatGPT")
        self.assertIn("已请求启动", r["message"])

    def test_missing_entry_does_not_start_anything(self):
        with patch.object(launcher.subprocess, "Popen") as p:
            r = launcher.launch_chatgpt([entry("Other", "X.Y_z!App")])
        self.assertFalse(r["ok"])
        p.assert_not_called()

    def test_launch_failure_propagates_error(self):
        with patch.object(launcher.subprocess, "Popen", side_effect=OSError("denied")):
            r = launcher.launch_chatgpt([entry("ChatGPT", "OpenAI.Sample_abc!App")])
        self.assertFalse(r["ok"])
        self.assertTrue(r["error"])


class TestApiConcurrency(unittest.TestCase):
    """Api.launch_chatgpt 必须与配置任务互斥，且不污染配置任务结果。"""

    def _api(self):
        import tempfile
        from pathlib import Path
        import app
        import core
        tmp = tempfile.TemporaryDirectory(prefix="launch-api-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / ".codex"
        (root / "configs").mkdir(parents=True)
        return app.Api(core.Paths(root, root / "configs"))

    def test_busy_rejects_without_launching(self):
        api = self._api()
        api._running = True
        with patch.object(launcher, "launch_chatgpt") as m:
            r = api.launch_chatgpt()
        self.assertFalse(r["ok"])
        self.assertIn("有操作正在执行", r["error"])
        m.assert_not_called()

    def test_releases_lock_even_when_launcher_raises(self):
        api = self._api()
        with patch.object(launcher, "launch_chatgpt", side_effect=RuntimeError("boom")):
            r = api.launch_chatgpt()
        self.assertFalse(r["ok"])
        self.assertFalse(api._running)
        # 释放后可再次调用，说明锁没有泄漏
        with patch.object(launcher, "launch_chatgpt", return_value={"ok": True, "message": "ok"}):
            self.assertTrue(api.launch_chatgpt()["ok"])

    def test_result_and_op_are_not_overwritten(self):
        """启动是短操作，不得覆盖配置任务的结果与操作名。"""
        api = self._api()
        api._result = {"keep": "config-task-result"}
        api._op = "switch"
        with patch.object(launcher, "launch_chatgpt", return_value={"ok": True, "message": "ok"}):
            api.launch_chatgpt()
        self.assertEqual(api._result, {"keep": "config-task-result"})
        self.assertEqual(api._op, "switch")
        self.assertFalse(api._running)

    def test_does_not_touch_config_files(self):
        api = self._api()
        live = api.p.live
        live.write_text('model = "before"\n', encoding="utf-8")
        before = live.read_bytes()
        with patch.object(launcher, "launch_chatgpt", return_value={"ok": True, "message": "ok"}):
            api.launch_chatgpt()
        self.assertEqual(live.read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""第一优先级回归：临时目录、合成密钥、传输 mock，禁止真实网络。"""
import json
import os
from pathlib import Path
import ssl
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

import app
import core
import connection

FORM = dict(model='test-model', model_provider='test_provider', base_url='https://provider.example/v1',
            env_key='P1_TEST_KEY', wire_api='responses', prov_name='测试供应商')
SECRET = 'synthetic-key-never-real'


class Priority1(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p1_')
        self.addCleanup(self.tmp.cleanup)
        self.p = core.Paths(self.tmp.name)
        self.env = patch.dict(os.environ, {'P1_TEST_KEY': SECRET})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.net = patch('connection.http.client.HTTPSConnection')
        self.http = self.net.start()
        self.addCleanup(self.net.stop)
        self.http.return_value.getresponse.return_value.status = 200
        self.socket = patch('socket.create_connection', side_effect=AssertionError('禁止真实网络'))
        self.socket.start()
        self.addCleanup(self.socket.stop)
        self.proc = patch('core.match_processes', return_value=[])
        self.proc.start()
        self.addCleanup(self.proc.stop)

    def files(self):
        return {str(f.relative_to(self.p.root)): f.read_bytes() for f in self.p.root.rglob('*') if f.is_file()}

    def create(self, name='a', kind='third_party', activate=False):
        return core.run_save_form(self.p, name, FORM, create_kind=kind, activate=activate)

    def test_official_clean_template(self):
        self.assertTrue(self.create('official', 'official')['ok'])
        text = core.read_text(core.preset_path(self.p, 'official'))
        self.assertNotIn('model_provider', text)
        self.assertNotIn('base_url', text)
        self.assertNotIn(SECRET, text)
        self.assertFalse(self.p.live.exists())
        self.assertFalse(self.p.state.exists())
        self.assertEqual(__import__('tomllib').loads(core.new_preset_text('official', {})), {})
        # IMP-026：官方模板 = 完全空白（连 model 都不写，交给宿主在打开时补齐）
        self.assertNotIn('model', text)
        self.assertTrue(all('=' not in line for line in text.splitlines()), text)
        # 即使表单里塞了字段，官方模板也必须忽略（界面不给，后端兜底）
        self.assertEqual(core.new_preset_text('official', FORM),
                         core.new_preset_text('official', {}))

    def test_custom_template_only_model_config(self):
        # IMP-026：自定义模型模板只写大模型相关设置，不掺入项目 / 插件等宿主设置
        self.assertTrue(self.create('custom', 'third_party')['ok'])
        text = core.read_text(core.preset_path(self.p, 'custom'))
        data = __import__('tomllib').loads(text)
        self.assertEqual(sorted(data.keys()), ['model', 'model_provider', 'model_providers'])
        self.assertEqual(list(data['model_providers'].keys()), [FORM['model_provider']])
        self.assertEqual(data['model_providers'][FORM['model_provider']]['base_url'], FORM['base_url'])
        for other in ('projects', 'plugins', 'mcp_servers', 'history', 'tui'):
            self.assertNotIn(other, text)

    def test_third_party_required_and_toml(self):
        for key in ('model', 'model_provider', 'base_url', 'env_key', 'wire_api'):
            with self.subTest(key=key), self.assertRaises(core.CoreError):
                core.new_preset_text('third_party', dict(FORM, **{key: ''}))
        data = __import__('tomllib').loads(core.new_preset_text('third_party', FORM))
        self.assertEqual(data['model_providers']['test_provider']['env_key'], 'P1_TEST_KEY')

    def test_no_overwrite_or_traversal(self):
        self.assertTrue(self.create()['ok'])
        before = self.files()
        self.assertFalse(self.create()['ok'])
        self.assertFalse(self.create('../evil')['ok'])
        self.assertEqual(before, self.files())

    def test_save_inactive_does_not_activate(self):
        self.create('a', activate=True)
        self.create('b')
        live, state = self.p.live.read_bytes(), self.p.state.read_bytes()
        r = core.run_save_form(self.p, 'b', dict(FORM, model='changed'))
        self.assertTrue(r['saved'])
        self.assertFalse(r['activated'])
        self.assertEqual(live, self.p.live.read_bytes())
        self.assertEqual(state, self.p.state.read_bytes())

    def test_current_preserves_external_then_edit_then_switch(self):
        self.create('a', activate=True)
        self.p.live.write_bytes(self.p.live.read_bytes() + b'\n[external]\nkeep = true\n')
        r = core.run_save_form(self.p, 'a', dict(FORM, model='edited', new_name='renamed'), activate=True)
        self.assertTrue(r['activated'])
        self.assertIn(b'keep = true', self.p.live.read_bytes())
        self.assertEqual(core.read_key(core.read_text(self.p.live), None, 'model'), 'edited')
        self.assertEqual(core.read_state(self.p)[0], 'renamed')
        self.create('b', 'official', activate=True)
        core.run_switch(self.p, 'renamed')
        self.assertEqual(core.read_key(core.read_text(self.p.live), None, 'model'), 'edited')
        self.assertTrue(list(self.p.hist_presets.rglob('*.toml')))
        self.assertTrue(list(self.p.hist_live.iterdir()))

    def test_activation_blocked_saved_not_enabled(self):
        self.create('a', activate=True)
        live, state = self.p.live.read_bytes(), self.p.state.read_bytes()
        with patch('core.match_processes', return_value=[{'pid':1, 'name':'codex.exe', 'path':''}]):
            r = self.create('b', activate=True)
            self.assertFalse(r['ok'])
            self.assertTrue(r['saved'])
            self.assertFalse(r['activated'])
            self.assertTrue(core.preset_path(self.p, 'b').exists())
            before = self.files()
            edit = core.run_save_form(self.p, 'a', dict(FORM, model='blocked'))
            self.assertFalse(edit['ok'])
            self.assertEqual(before, self.files())
        self.assertEqual(live, self.p.live.read_bytes())
        self.assertEqual(state, self.p.state.read_bytes())

    def test_new_top_key_before_section(self):
        text = core.set_key('[windows]\nsandbox = "unelevated"\n', None, 'model', 'x')
        self.assertEqual(__import__('tomllib').loads(text)['model'], 'x')
        self.assertNotIn('[]', text)

    def test_local_and_prepare_zero_network_zero_writes(self):
        before = self.files()
        self.assertTrue(connection.local_check(FORM)['ok'])
        self.assertFalse(connection.local_check({})['network_allowed'])
        api = app.Api(self.p)
        r = api.prepare_connection(FORM)
        self.assertTrue(r['ok'])
        self.assertNotIn(SECRET, json.dumps(r))
        self.http.assert_not_called()
        self.assertEqual(before, self.files())

    def test_missing_env_and_invalid_urls(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(connection.local_check(FORM)['ok'])
        for url in ('http://provider.example', 'https://user:pass@provider.example', 'https://provider.example?key=secret',
                    'https://provider.example#secret', 'https://', 'https://provider.example:99999',
                    'https://provider.example/\nsecret', 'https://provider.example\\evil'):
            with self.subTest(url=url):
                self.assertFalse(connection.local_check(dict(FORM, base_url=url))['ok'])
        self.http.assert_not_called()

    def test_unconfirmed_zero_network(self):
        for confirmed in (False, None, 'true', 1):
            self.assertFalse(connection.test_connection(FORM, confirmed=confirmed)['ok'])
        self.http.assert_not_called()

    def test_https_tls_timeout_payload_env(self):
        before = self.files()
        self.assertTrue(connection.test_connection(FORM, confirmed=True)['ok'])
        args, kw = self.http.call_args
        self.assertEqual(args, ('provider.example', 443))
        self.assertEqual(kw['timeout'], 12)
        self.assertTrue(kw['context'].check_hostname)
        self.assertEqual(kw['context'].verify_mode, ssl.CERT_REQUIRED)
        args, kw = self.http.return_value.request.call_args
        self.assertEqual(args, ('POST', '/v1/responses'))
        self.assertEqual(kw['headers']['Authorization'], 'Bearer ' + SECRET)
        payload = json.loads(kw['body'])
        self.assertEqual(payload['input'], 'Reply OK.')
        self.assertEqual(payload['max_output_tokens'], 16)
        self.assertFalse(payload['store'])
        self.assertNotIn(SECRET, kw['body'].decode())
        self.assertEqual(before, self.files())
        self.http.return_value.getresponse.return_value.read.assert_not_called()

    def test_chat_payload(self):
        self.assertTrue(connection.test_connection(dict(FORM, wire_api='chat'), confirmed=True)['ok'])
        args, kw = self.http.return_value.request.call_args
        self.assertEqual(args[1], '/v1/chat/completions')
        self.assertEqual(json.loads(kw['body'])['max_tokens'], 16)

    def test_redirect_never_followed(self):
        for status in (301, 302, 303, 307, 308):
            self.http.reset_mock()
            self.http.return_value.getresponse.return_value.status = status
            r = connection.test_connection(FORM, confirmed=True)
            self.assertFalse(r['ok'])
            self.assertIn('跳转', r['message'])
            self.assertEqual(self.http.call_count, 1)
            self.assertEqual(self.http.return_value.request.call_count, 1)
            self.http.return_value.getresponse.return_value.getheader.assert_not_called()

    def test_redacted_error_no_retry(self):
        for error in (ssl.SSLError(SECRET), TimeoutError(SECRET), OSError(SECRET), RuntimeError(SECRET)):
            self.http.reset_mock()
            self.http.return_value.request.side_effect = error
            r = connection.test_connection(FORM, confirmed=True)
            self.assertFalse(r['ok'])
            self.assertNotIn(SECRET, json.dumps(r))
            self.assertEqual(self.http.return_value.request.call_count, 1)
            self.http.return_value.close.assert_called_once()

    def test_status_redaction(self):
        for status in (401, 403, 404, 429, 500):
            self.http.return_value.getresponse.return_value.status = status
            r = connection.test_connection(FORM, confirmed=True)
            self.assertFalse(r['ok'])
            self.assertEqual(r['status'], status)
            self.assertNotIn(SECRET, json.dumps(r))

    def test_confirmation_one_use_expiry_bound_form(self):
        api = app.Api(self.p)
        self.assertIn('error', api.run('connection', None, {'confirmed':True}))
        form = dict(FORM)
        prepared = api.prepare_connection(form)
        form['base_url'] = 'https://other.example'
        token = prepared['token']
        self.assertTrue(api.run('connection', None, {'token':token, 'confirmed':True})['started'])
        deadline = time.monotonic()+3
        while api.poll()['running'] and time.monotonic()<deadline:
            time.sleep(.01)
        self.assertTrue(api.poll()['result']['ok'])
        self.assertEqual(self.http.call_args.args[0], 'provider.example')
        self.assertNotIn(SECRET, json.dumps(api.poll()))
        self.assertIn('error', api.run('connection', None, {'token':token,'confirmed':True}))
        token = api.prepare_connection(FORM)['token']
        with patch('app.time.monotonic', return_value=time.monotonic()+121):
            self.assertIn('error', api.run('connection',None,{'token':token,'confirmed':True}))

    def test_activation_requires_confirmation(self):
        api = app.Api(self.p)
        r = api.run('save_form','a',{'form_json':json.dumps(FORM),'activate':True,'create_kind':'third_party'})
        self.assertIn('error',r)
        self.assertEqual(self.files(),{})

    def test_history_list_preview_and_noncurrent_restore(self):
        self.create('a', activate=True)
        self.create('b')
        target = core.preset_path(self.p, 'b')
        original = target.read_bytes()
        hist = self.p.hist_presets / 'b' / '20260916-010101.toml'
        hist.parent.mkdir(parents=True)
        hist.write_bytes(b'model = "history-b"\n')
        rows = core.list_history(self.p)
        row = next(x for x in rows if x['path'] == str(hist.resolve()))
        self.assertEqual((row['source'], row['preset'], row['size']), ('preset', 'b', hist.stat().st_size))
        live_before = self.p.live.read_bytes()
        state_before = self.p.state.read_bytes()
        pv = core.preview_history(self.p, hist, 'preset', 'b')
        self.assertFalse(pv['same'])
        r = core.run_restore_history(self.p, hist, 'preset', 'b')
        self.assertTrue(r['ok'])
        self.assertEqual(target.read_bytes(), hist.read_bytes())
        self.assertEqual(self.p.live.read_bytes(), live_before)
        self.assertEqual(self.p.state.read_bytes(), state_before)
        backups = list((self.p.hist_presets / 'b').glob('*.toml'))
        self.assertTrue(any(x.read_bytes() == original for x in backups if x != hist))
        self.assertTrue(hist.exists())

    def test_restore_current_and_live_require_host_exit(self):
        self.create('a', activate=True)
        current_hist = self.p.hist_presets / 'a' / '20260916-020202.toml'
        current_hist.parent.mkdir(parents=True)
        current_hist.write_bytes(b'model = "old-current"\n')
        live_hist = self.p.hist_live / 'config.toml.20260916-020203'
        live_hist.parent.mkdir(parents=True, exist_ok=True)
        live_hist.write_bytes(b'model = "old-live"\n')
        before = self.files()
        with patch('core.match_processes', return_value=[{'pid':1,'name':'codex.exe','path':''}]):
            self.assertTrue(core.run_restore_history(self.p, current_hist, 'preset', 'a')['blocked'])
            self.assertTrue(core.run_restore_history(self.p, live_hist, 'live')['blocked'])
        self.assertEqual(before, self.files())
        with patch('core.match_processes', return_value=[]):
            self.assertTrue(core.run_restore_history(self.p, current_hist, 'preset', 'a')['ok'])
        self.assertEqual(self.p.live.read_bytes(), current_hist.read_bytes())
        self.assertEqual(core.preset_path(self.p, 'a').read_bytes(), current_hist.read_bytes())

    def test_history_path_and_change_checks(self):
        self.create('a')
        outside = Path(self.tmp.name) / 'outside.toml'
        outside.write_text('model="x"\n', encoding='utf-8')
        with self.assertRaises(core.CoreError):
            core.preview_history(self.p, outside, 'preset', 'a')
        hist = self.p.hist_presets / 'a' / '20260916-030303.toml'
        hist.parent.mkdir(parents=True)
        hist.write_bytes(b'model="old"\n')
        st = hist.stat()
        digest = __import__('hashlib').sha256(hist.read_bytes()).hexdigest()
        hist.write_bytes(b'model="changed"\n')
        before = core.preset_path(self.p, 'a').read_bytes()
        r = core.run_restore_history(self.p, hist, 'preset', 'a',
                                     expected_size=st.st_size,
                                     expected_mtime_ns=st.st_mtime_ns,
                                     expected_sha256=digest)
        self.assertFalse(r['ok'])
        self.assertEqual(core.preset_path(self.p, 'a').read_bytes(), before)

    def test_copy_is_byte_exact_and_never_activates(self):
        self.create('a', activate=True)
        source = core.preset_path(self.p, 'a')
        live, state = self.p.live.read_bytes(), self.p.state.read_bytes()
        r = core.run_copy_preset(self.p, 'a', 'a-copy')
        self.assertTrue(r['ok'])
        self.assertEqual(source.read_bytes(), core.preset_path(self.p, 'a-copy').read_bytes())
        self.assertEqual((live, state), (self.p.live.read_bytes(), self.p.state.read_bytes()))
        self.assertFalse(core.run_copy_preset(self.p, 'a', 'a-copy')['ok'])
        self.assertFalse(core.run_copy_preset(self.p, 'a', '../bad')['ok'])

    def test_delete_noncurrent_backups_and_current_refused(self):
        self.create('a', activate=True)
        self.create('b')
        live, state = self.p.live.read_bytes(), self.p.state.read_bytes()
        self.assertFalse(core.run_delete_preset(self.p, 'a')['ok'])
        source = core.preset_path(self.p, 'b').read_bytes()
        existing_hist = self.p.hist_presets / 'b' / 'old.toml'
        existing_hist.parent.mkdir(parents=True, exist_ok=True)
        existing_hist.write_bytes(b'keep-history')
        with patch('core.match_processes', return_value=[{'pid':1,'name':'codex.exe','path':''}]):
            r = core.run_delete_preset(self.p, 'b')
        self.assertTrue(r['ok'])
        self.assertFalse(core.preset_path(self.p, 'b').exists())
        self.assertTrue(existing_hist.exists())
        self.assertTrue(any(x.read_bytes() == source for x in (self.p.hist_presets/'b').glob('*.toml')))
        self.assertEqual((live, state), (self.p.live.read_bytes(), self.p.state.read_bytes()))

    def test_history_api_uses_opaque_tokens_and_one_use_restore(self):
        self.create('a', activate=True)
        hist = self.p.hist_live / 'config.toml.20260916-040404'
        hist.parent.mkdir(parents=True, exist_ok=True)
        hist.write_bytes(b'model="api-history"\n')
        api = app.Api(self.p)
        listed = api.history_list()
        self.assertTrue(listed['ok'])
        self.assertNotIn(str(self.p.root), json.dumps(listed, ensure_ascii=False))
        token = next(x['id'] for x in listed['items'] if x['source'] == 'live')
        pv = api.history_preview(token, 'live', '')
        self.assertTrue(pv['ok'])
        self.assertIn('confirm_token', pv)
        started = api.run('restore', None, {'token':pv['confirm_token'], 'confirmed':True})
        self.assertTrue(started['started'])
        deadline = time.monotonic()+3
        while api.poll()['running'] and time.monotonic()<deadline:
            time.sleep(.01)
        self.assertTrue(api.poll()['result']['ok'])
        self.assertIn('error', api.run('restore', None, {'token':pv['confirm_token'], 'confirmed':True}))


if __name__ == '__main__':
    unittest.main(verbosity=2)

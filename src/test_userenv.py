# -*- coding: utf-8 -*-

# --- 输出编码：CI（windows-latest）控制台默认 cp1252，中文断言名会 UnicodeEncodeError ---
import sys as _sys_enc
try:
    _sys_enc.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_enc.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import os, sys, unittest
from unittest.mock import patch, call
sys.path.insert(0, os.path.dirname(__file__))
import userenv

class UserEnvTests(unittest.TestCase):
    def test_suggest_provider(self): self.assertEqual(userenv.suggest_name('example','x'),'EXAMPLE_API_KEY')
    def test_suggest_name(self): self.assertEqual(userenv.suggest_name('','my-config'),'MY_CONFIG_API_KEY')
    def test_suggest_chinese_stable(self):
        a=userenv.suggest_name('','测试服务'); b=userenv.suggest_name('','测试服务')
        self.assertEqual(a,b); self.assertRegex(a,r'^CODEX_[A-F0-9]{12}_API_KEY$')
    def test_existing_suffix(self): self.assertEqual(userenv.suggest_name('ABC_API_KEY',''),'ABC_API_KEY')
    def test_validate(self):
        userenv.validate('OK_KEY','secret')
        for n in ('1BAD','A-B',''):
            with self.assertRaises(userenv.EnvironmentError): userenv.validate(n,'x')
        with self.assertRaises(userenv.EnvironmentError): userenv.validate('OK','x\nleak')
    @patch('userenv.broadcast')
    @patch('userenv.write_value')
    @patch('userenv.read_value', return_value=None)
    def test_save_success(self, read, write, broadcast):
        old=os.environ.pop('UT_CODEX_KEY',None)
        try:
            r=userenv.save('UT_CODEX_KEY','hidden',userenv.fingerprint(None),lambda:{'ok':True,'saved':True})
            self.assertTrue(r['ok']); self.assertEqual(os.environ['UT_CODEX_KEY'],'hidden')
            write.assert_called_once(); broadcast.assert_called_once()
        finally:
            if old is None: os.environ.pop('UT_CODEX_KEY',None)
            else: os.environ['UT_CODEX_KEY']=old
    @patch('userenv.broadcast')
    @patch('userenv.write_value')
    @patch('userenv.read_value', return_value=('old',1))
    def test_config_failure_rolls_back(self, read, write, broadcast):
        old=os.environ.get('UT_CODEX_KEY'); os.environ['UT_CODEX_KEY']='old-process'
        try:
            with self.assertRaises(userenv.EnvironmentError):
                userenv.save('UT_CODEX_KEY','hidden',userenv.fingerprint(('old',1)),lambda:{'ok':False,'saved':False})
            self.assertEqual(os.environ['UT_CODEX_KEY'],'old-process')
            self.assertEqual(write.call_args_list[-1],call('UT_CODEX_KEY',('old',1)))
        finally:
            if old is None: os.environ.pop('UT_CODEX_KEY',None)
            else: os.environ['UT_CODEX_KEY']=old

if __name__=='__main__': unittest.main(verbosity=2)

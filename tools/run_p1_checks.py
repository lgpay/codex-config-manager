"""每个旧套件在独立子进程运行；网络出口封锁，API Key 替换为合成值。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# 使用启动本脚本的解释器，避免绑定开发者本机的 WorkBuddy/Python 路径。
# GUI 套件需由已安装 pywebview 的 Windows Python 环境启动。
PYTHON = Path(sys.executable)
SUITES = {
    'core': ['src/test_core.py','src/test_roundtrip.py','tools/t_toml.py','tools/t_edit.py','tools/t_cli.py','src/test_priority1.py'],
    'gui': ['tools/t_gui_imp.py','tools/t_gui_edit.py','tools/t_gui_p1.py'],
}
mode = sys.argv[1]
results = []
for suite in SUITES[mode]:
    if not (ROOT/suite).exists():
        raise SystemExit('缺少测试：'+suite)
    env = dict(os.environ, PYTHONIOENCODING='utf-8', EXAMPLE_API_KEY='synthetic-test-only', P1_TEST_KEY='synthetic-test-only')
    for k in list(env):
        if ('API_KEY' in k.upper() or k.upper().endswith('_TOKEN')) and k != 'EXAMPLE_API_KEY':
            env.pop(k)
    with tempfile.TemporaryDirectory(prefix='p1_suite_') as tmp:
        env['CODEX_HOME'] = tmp
        wrapper = "import sys,runpy,socket; from unittest.mock import patch; script,src=sys.argv[1],sys.argv[2]; sys.path.insert(0,src); sys.argv=[script]; real=socket.create_connection; safe=lambda address,*a,**k: real(address,*a,**k) if str(address[0]).lower() in ('127.0.0.1','localhost','::1') else (_ for _ in ()).throw(AssertionError('测试禁止真实外网')); p=patch('socket.create_connection',side_effect=safe); p.start(); runpy.run_path(script,run_name='__main__')"
        try:
            r = subprocess.run([str(PYTHON), '-c',wrapper,str(ROOT/suite),str(ROOT/'src')],
                               env=env,cwd=ROOT,capture_output=True,timeout=150)
            out = r.stdout.decode('utf-8','replace')+r.stderr.decode('utf-8','replace')
            code = r.returncode
        except subprocess.TimeoutExpired:
            out, code = '测试超时，需检查并关闭测试窗口。', 124
        log = ROOT/'outputs'/('p1-'+Path(suite).stem+'.txt')
        log.write_text(out,encoding='utf-8')
        results.append({'suite':suite,'returncode':code,'log':str(log)})
        print(suite, '退出码',code,flush=True)
        print('\n'.join(out.splitlines()[-5:]),flush=True)
(ROOT/'outputs'/('p1-'+mode+'-summary.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
sys.exit(1 if any(r['returncode'] for r in results) else 0)

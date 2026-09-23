"""Exercise the installed PowerShell entry point and byte-exact retrieval."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
runtime = ROOT/'.harness/runtime'
runtime.mkdir(parents=True, exist_ok=True)
launcher = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT/'scripts/Invoke-HarnessJson.ps1')]
rows = [{'id': ('long_identifier_' + 'x'*270 if i == 257 else 'row_') + str(i), 'status': 'pending' if i == 333 else 'ok',
         'index': i, 'label': 'Проверка JSON'} for i in range(600)]
raw = (json.dumps(rows, ensure_ascii=False, indent=2) + '\r\n').encode('utf-8')
key = hashlib.sha256(raw).hexdigest()
with tempfile.TemporaryDirectory(dir=runtime, prefix='json-smoke-') as temporary:
    source = Path(temporary)/'input.json'
    source.write_bytes(raw)
    result = subprocess.run([*launcher, 'compress', str(source)], cwd=ROOT, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    output = result.stdout.decode('utf-8')
    assert 'format=table' in output, 'expected verified Headroom table: ' + result.stderr.decode(errors='replace')
    assert '<<ccr:' not in output
    assert all(row['id'] in output for row in rows)
    restored = subprocess.run([*launcher, 'retrieve', key], cwd=ROOT, capture_output=True, timeout=60)
    assert restored.returncode == 0, restored.stderr.decode(errors='replace')
    assert restored.stdout == raw, 'launcher did not preserve original bytes'
    print(f'PASS installed launcher: 600 IDs inline, strict lossless table, exact SHA-256 retrieval {key}')

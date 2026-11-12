"""Check the published source, input, model and library bytes before reproduction."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'reproducibility/FILES.sha256.json').read_text())
failures = []
for name, expected in manifest.items():
    path = root / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        failures.append(name)
if failures:
    raise SystemExit('Changed or missing published files:\n' + '\n'.join(failures))
print(f'Verified {len(manifest)} published files. Generated outputs are outside this manifest.')

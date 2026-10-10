"""Recover native hero ability coefficients for exploration admission."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd()))
from analysis.progression.probe import read_tables

data, meta, missing = read_tables(['AttribType', 'PlayerAttrib'])
if missing:
    raise ValueError(missing)
params = {r['Key']: r.get('Value', '') for r in json.loads(
    Path('runtime/globalparamstring.json').read_text(encoding='utf8'))}
result = {'sources': meta, 'attributes': data['AttribType'], 'heroes': data['PlayerAttrib'],
          'params': {k: v for k, v in params.items() if k.startswith('Skill') and k.endswith('Ability')
                     or k in ('CRI', 'CRI_Dmg', 'SR_Max')}}
Path('src/x2server/data/college_power_rules.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print('Exported', len(data['AttribType']), 'attributes,', len(data['PlayerAttrib']), 'heroes', result['params'])

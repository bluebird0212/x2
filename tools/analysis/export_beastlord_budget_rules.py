"""Export approved beastlord value caps from official tables, without live DB access."""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from analysis.progression.probe import read_tables
from x2server.player.battle_entry import SECTION_TYPES

VERSION = 'beastlord-3000-20261010'
BASE = 3000
CURVE = [100, 106, 113, 121, 131, 143, 158, 177, 200, 440]


def number(value):
    return value.get('value', 0) if isinstance(value, dict) else (value or 0)


def export():
    tables, sources, missing = read_tables(['SectionTable', 'Item'])
    if missing:
        raise ValueError(missing)
    equipment = json.loads((ROOT / 'src/x2server/data/equipment_tables.json').read_text(encoding='utf8'))['equib_base']
    canonical = {int(key) for key in equipment}
    beasts = {r['ItemID'] for r in tables['Item'] if number(r.get('ItemType')) == 10
              and r.get('AddADCGroup') == 5 and r['ItemID'] in canonical}
    entries, audit = {}, []
    counts = {'sections': 0, 'explicit_beastlord': 0, 'official_rate': 0,
              'compatibility_curve': 0, 'battlepass_unchanged': 0,
              'unknown_difficulty_unchanged': 0, 'group_only_unchanged': 0,
              'no_beastlord_unchanged': 0}
    for row in tables['SectionTable']:
        sid = row['SectionID']
        difficulty, kind = number(row.get('DifficultyLevel')), number(row.get('Type'))
        allowed = sorted(beasts.intersection(row.get('DroopLimit', [])))
        shown = sorted(beasts.intersection(row.get('DroopDisplay', [])))
        eligible = bool(allowed or shown)
        old = 1000 if 1 <= difficulty <= 3 else 5000 if difficulty >= 7 else 3000
        match = re.search(r'(\d+)%\s*兽主掉落奖励', row.get('NameMoreChina', ''))
        percent, source, budget = None, 'no_beastlord_unchanged', old
        counts['sections'] += 1
        counts['explicit_beastlord'] += eligible
        # User explicitly requires every Battlepass budget to stay unchanged,
        # including any future Battlepass row carrying a percentage description.
        if eligible and kind == 20:
            source = 'battlepass_unchanged'
        elif eligible and match:
            percent, source = int(match.group(1)), 'official_rate'
        elif eligible and 1 <= difficulty <= 10:
            percent, source = CURVE[difficulty - 1], 'compatibility_curve'
        elif eligible:
            source = 'unknown_difficulty_unchanged'
        elif 5 in row.get('DroopLimit2', []):
            source = 'group_only_unchanged'
        counts[source] += 1
        if percent is not None:
            budget = BASE * percent // 100  # Official rates are integer percent; BASE is divisible by 100.
            entries[str(sid)] = {'percent': percent, 'budget': budget, 'source': source,
                                 'difficulty': difficulty, 'section_type': kind}
        audit.append({'SectionID': sid, 'name': row.get('NameChina', ''),
                      'type': SECTION_TYPES.get(kind, str(kind)), 'difficulty': difficulty,
                      'source': source, 'DropValueID': row.get('DropValueID', 0),
                      'beastlord_whitelist': ';'.join(map(str, allowed)),
                      'star_limits': str(row.get('DroopLimit3', [])),
                      'percent': percent or '', 'old_group5': old, 'new_group5': budget,
                      'delta': budget - old})
    assert counts['sections'] == len({r['SectionID'] for r in audit})
    result = {'version': VERSION, 'base_100_percent': BASE, 'group': 5,
              'compatibility_curve_percent': CURVE,
              'approval': 'USER_DECISION 2026-10-10: 100%=3000; Battlepass unchanged',
              'sources': {k: {'source': v['source'], 'record_count': v['record_count']} for k, v in sources.items()},
              'coverage': counts, 'sections': entries}
    target = ROOT / 'src/x2server/data/beastlord_budget_rules.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    with (ROOT / 'analysis/equipment/beastlord_budget_implemented_20261010.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(audit[0]))
        writer.writeheader()
        writer.writerows(audit)
    print(json.dumps(counts))


if __name__ == '__main__':
    export()

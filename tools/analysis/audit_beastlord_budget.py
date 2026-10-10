"""Compare official moon descriptions with Revival's actual value caps."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from analysis.progression.probe import read_tables
from x2server.player.battle_entry import BattleEntryCatalog
from x2server.player.drop_budget import DropBudgetCompatibilityPolicy

tables, sources, missing = read_tables(['SectionTable', 'Item'])
if missing:
    raise ValueError(missing)
sections = BattleEntryCatalog().sections
policy = DropBudgetCompatibilityPolicy({k: r.get('DifficultyLevel', 0) for k, r in sections.items()})
items = {r['ItemID']: r for r in tables['Item']}
stages = json.loads((ROOT / 'src/x2server/data/equipment_tables.json').read_text(encoding='utf8'))['equib_stage']
rows = []
for row in tables['SectionTable']:
    sid = row['SectionID']
    if not 2133101 <= sid <= 2133110:
        continue
    advertised = int(re.search(r'(\d+)%兽主掉落奖励', row['NameMoreChina']).group(1))
    equipment = [items[i] for i in row.get('DroopLimit', []) if i in items and items[i].get('ItemType', {}).get('value') == 10]
    costs = sorted({int(stages['6']['equib_value'] * item['ItemValue'] / 1000) for item in equipment})
    rows.append({'section_id': sid, 'name': row['NameChina'],
                 'advertised_percent': advertised, 'difficulty': sections[sid]['DifficultyLevel'],
                 'quality_band': row['DroopLimit3'], 'drop_value_id': row['DropValueID'],
                 'beastlord_group': 5, 'budget': policy.budget_for(sid)[5],
                 'six_star_item_value_costs': costs,
                 'six_star_only_count_caps': [policy.budget_for(sid)[5] // cost for cost in costs if cost > 0]})
result = {'sources': sources, 'official_budget_values': 'SERVER_DATA_LOST',
          'policy': 'USER_DECISION 2026-09-26 LOW=1000/MID=3000/HIGH=5000 per group',
          'native_consumer': 'JudgeDropItem 0x1e49838: cumulative weighted value <= dropValues[AddADCGroup]',
          'rows': rows,
          'conclusion': 'Blood moon and Hui moon both cap group 5 at 5000. This cap does not represent a 440/200 yield ratio; actual counts depend on client candidate rolls, stars, values and kills. No difficulty multiplier is added by the server.',
          'budget_change': 'none; exact official values are unknown and the existing tier policy is user-approved'}
target = ROOT / 'analysis/equipment/beastlord_budget_audit.json'
target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps(rows[-2:]))

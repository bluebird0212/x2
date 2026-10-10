"""Audit existing budget behavior; these tests do not declare an official quota."""
import asyncio
import pytest
from tests.unit.test_battle import packet, request
from x2server.messages.battle import DROP_DATA, FIGHT_DATA
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.player.store import PlayerStore


@pytest.mark.parametrize('section,difficulty', [(2133109, 9), (2133110, 10)])
def test_hui_and_blood_moon_entry_and_refresh_budget_agree(tmp_path, section, difficulty):
    store = PlayerStore(tmp_path / 'beastlord.db')
    p = store.login('audit', 1, 0)
    store.save_snapshot(1, dict(p['snapshot'], level=60, mobility={'power': 150},
        heroes=[{'id': 1003, 'state': 2, 'level': 1, 'star': 1}]), p['revision'])
    ctx = DispatchContext('audit', 'local', SessionState('audit', 'session', player_id=1))
    economy = EconomyService(store)
    battle = BattleService(store, economy)
    row = battle.catalog.sections[section]
    assert row['DifficultyLevel'] == difficulty
    with store.db:
        for prerequisite in (row.get('OpenParam'), section - 1):
            if prerequisite:
                store.db.execute('INSERT OR IGNORE INTO economy_clears VALUES (?,?,?)', (1, prerequisite, 'audit-prerequisite'))
    values = request()
    values.update(missionId=section, chapter=row['ChapterID'], sceneId=row['Maps'][0])
    response = asyncio.run(battle.enter(ctx, packet(values)))
    assert response.values['result'] == 10
    entry_budget = DROP_DATA.decode(FIGHT_DATA.decode(response.values['data'])['dropData'])['dropValues']
    refreshed = asyncio.run(battle.drop_data(ctx, packet({'missionId': section,
        'chapterId': row['ChapterID']}, request_id=2, name='C2L_FightDropData')))
    assert refreshed.values['result'] == 10
    refresh_budget = DROP_DATA.decode(refreshed.values['data'])['dropValues']
    assert entry_budget == refresh_budget == [5000] * 27
    assert entry_budget[5] == 5000  # Beastlord value cap, not item count.
    store.close()

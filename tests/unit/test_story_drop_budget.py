import asyncio
import json
from pathlib import Path
from tests.unit.test_economy import env
from tests.unit.test_battle import packet, request
from x2server.messages.battle import DROP_DATA, FIGHT_DATA, BATTLE_SCHEMAS, OUTSIDE_ITEM, CHECKOUT
from x2server.player.battle import BattleService
from x2server.player.drop_budget import STORY_GROUP_BUDGET


def test_official_story_items_have_a_reachable_value_budget(env):
    _, economy, _ = env
    evidence = json.loads((Path(__file__).resolve().parents[2] /
                          'analysis/equipment/story_drop_budget_20261010.json').read_text(encoding='utf8'))
    grouped = evidence['items']
    assert len(grouped) == 25
    story = [row for row in grouped if row['ItemType']['value'] in (25,14)]
    assert len(story) == 13  # 12 story items plus one story gift.
    assert all(row['ItemUseScence']['value'] == 1 for row in grouped)
    assert {row['ItemValue'] for row in story} == {1}
    values = BattleService(env[0],economy).drop_budget.budget_for(2110605)
    # Cover all canonical story rows, not only the battery reported in chapter 1.
    assert len(values) > max(row['AddADCGroup'] for row in story)
    assert values[27] == STORY_GROUP_BUDGET
    assert sum(row['ItemValue'] for row in story) <= values[27]
    # A new array entry does not bypass unavailable legacy event item limits.
    assert all(row['ItemValue'] > values[27] for row in grouped if row['ItemValue'] == 9999)
    # The compact settlement catalog already recognizes these items even though
    # it omits AddADCGroup. Keep that existing path rather than inventing grants.
    assert all(economy.items[row['ItemID']]['ItemType']['value'] == row['ItemType']['value'] for row in story)


def test_legacy_27_group_run_is_accepted_without_budget_topup(env):
    store, economy, ctx = env
    battle = BattleService(store,economy)
    entered = asyncio.run(battle.enter(ctx,packet(request())))
    data = FIGHT_DATA.decode(entered.values['data'])
    drop = DROP_DATA.decode(data['dropData'])
    drop['dropValues'] = [100 + i for i in range(27)]
    data['dropData'] = DROP_DATA.encode(drop)
    with store.db:
        store.db.execute('UPDATE battle_entries SET response=? WHERE uuid=?',
                         (BATTLE_SCHEMAS['L2C_FightData'].encode(
                             {**entered.values,'data':FIGHT_DATA.encode(data)}), entered.values['uuid']))
    for _ in range(2):
        answer = asyncio.run(battle.drop_data(ctx,packet(
            {'missionId':2110801,'chapterId':2010100},name='C2L_FightDropData')))
        assert answer.values['result'] == 10
        assert DROP_DATA.decode(answer.values['data'])['dropValues'] == drop['dropValues']


def test_story_pickup_settlement_and_replay(env):
    store, economy, ctx = env
    battle = BattleService(store,economy)
    section = 2110605
    static = battle.catalog.sections[section]
    values = request()
    values.update(missionId=section,chapter=static['ChapterID'],sceneId=static['Maps'][0])
    entered = asyncio.run(battle.enter(ctx,packet(values)))
    assert entered.values['result'] == 10
    checkout = packet({'checkout':CHECKOUT.encode({'chapterId':static['ChapterID'],'sectionId':section,
        'success':True,'fightTime':200,
        'outsideItems':[OUTSIDE_ITEM.encode({'id':1101014,'num':1,'quality':1})]})},
        name='C2L_CheckoutMainMissionSign',request_id=10)
    answer = asyncio.run(battle.checkout(ctx,checkout))
    assert answer.values['result'] == 10
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1101014').fetchone()[0] == 1
    assert asyncio.run(battle.checkout(ctx,checkout)).values == answer.values
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1101014').fetchone()[0] == 1

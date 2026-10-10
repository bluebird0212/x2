"""Wonder unlock, timed progression and real battle attributes on isolated saves."""
import asyncio
import pytest

from tests.unit.test_college_upgrade import game, send, quantity
from tests.unit.test_battle import packet, request
from x2server.player.battle import BattleService
from x2server.player.battle_bonuses import other_attributes, catalog
from x2server.player.college import CollegeStateRepository
from x2server.player.store import PlayerStore
from x2server.messages.battle import PROFILE_HERO, FIGHT_DATA, FIGHT_HERO, HERO_ATTR_ADD
from x2server.messages.lobby import BUILDING_BASE_INFO, WONDER_QUEUE


def seed_heroes(game, ids=(1010, 1014), star=1):
    player = game[0].get(1)
    heroes = [dict(id=hid, state=2, level=1, star=star, exp=0) for hid in ids]
    game[0].save_snapshot(1, dict(player['snapshot'], heroes=heroes), player['revision'])
    return heroes


def test_wonder_unlock_upgrade_speed_offline_battle_and_star(game, monkeypatch):
    store, clock, repo, service, context = game
    monkeypatch.setattr('x2server.player.server_clock.ServerClock.now', lambda self: clock.now())
    assert send(game, 'BuildingUpgrade', bid=721, kind=2).values['code'] == 57
    assert send(game, 'BuildStarUP', bid=721, kind=2).values['code'] == 68
    heroes = seed_heroes(game)
    assert other_attributes(store, 1, heroes[0], clock) == {}
    unlock = send(game, 'BuildStarUP', bid=721, kind=2, seq=2)
    assert unlock.values['code'] == 10 and unlock.values['star'] == 1
    assert quantity(store, 1237801) == 88
    assert send(game, 'BuildStarUP', bid=721, kind=2, seq=2).values == unlock.values
    assert quantity(store, 1237801) == 88
    assert other_attributes(store, 1, heroes[0], clock) == {100: 52}
    assert other_attributes(store, 1, {'id': 1003}, clock) == {}
    state = repo.load(1)
    state['buildings'][0]['buildingLevel'] = 5
    repo.save(1, state)
    upgrade = send(game, 'BuildingUpgrade', bid=721, kind=2, seq=3)
    assert upgrade.values['code'] == 10 and upgrade.values['buildTime'] == 3600
    assert WONDER_QUEUE.decode(upgrade.before_response[0].values['wonderQueue'])['buildingId'] == 721
    assert other_attributes(store, 1, heroes[0], clock) == {100: 52}
    assert send(game, 'BuildingUpgrade', bid=722, kind=2, seq=4).values['code'] == 55
    # Ordinary and wonder queues are independent.
    assert send(game, 'BuildingUpgrade', bid=702, seq=5).values['code'] == 10
    speed = send(game, 'BuildSpeedUP', bid=721, kind=2, seq=6, itemId=1237832, itemNum=1)
    assert speed.values['code'] == 10 and speed.values['buildStatus'] == 1
    assert other_attributes(store, 1, heroes[0], clock) == {100: 71}
    assert send(game, 'BuildingUpgrade', bid=721, kind=2, seq=7).values['code'] == 10
    restored = PlayerStore(store.path)
    clock.value += 5400
    # Enter combat directly after reconnect, without querying College first.
    battle = BattleService(restored)
    values = request()
    values['heros'] = [PROFILE_HERO.encode({'heroId': 1010, 'leader': 1})]
    response = asyncio.run(battle.enter(context, packet(values)))
    assert response.values['result'] == 10
    fighter = FIGHT_HERO.decode(FIGHT_DATA.decode(response.values['data'])['fightHeros'][0])
    attrs = {p['attrId']: p['attrValue'] for p in map(HERO_ATTR_ADD.decode, fighter['attrAdd'])}
    assert attrs[100] == 92  # Wonder additive carrier; bare growth stays separate.
    assert other_attributes(restored, 1, heroes[0], clock) == {100: 92}
    assert CollegeStateRepository(restored, clock).load(1)['wonders'][0]['buildingLevel'] == 3
    restored.close()
    assert send(game, 'BuildStarUP', bid=721, kind=2, seq=8).values['code'] == 68
    heroes = seed_heroes(game, star=3)  # two big stars each = required total four
    assert send(game, 'BuildStarUP', bid=721, kind=2, seq=8).values['code'] == 56
    for level, seq in ((4, 9), (5, 10)):
        assert send(game, 'BuildingUpgrade', bid=721, kind=2, seq=seq).values['code'] == 10
        clock.value = repo.load(1)['wonder_queue']['upgradeEndTime']
        messages = service.upgrades.complete_due(1)
        assert any(m.message_name == 'L2C_UpLevelBuildingId' and m.values['buildingId'] == 721 for m in messages)
        assert service.upgrades.complete_due(1) == ()
    assert send(game, 'BuildingUpgrade', bid=721, kind=2, seq=11).values['code'] == 57
    assert send(game, 'BuildStarUP', bid=721, kind=2, seq=12).values['code'] == 10
    assert other_attributes(store, 1, heroes[0], clock) == {100: 137, 104: 238}


@pytest.mark.parametrize('bid', range(721, 728))
def test_all_open_wonders_match_civilization_unlock_and_big_star_conditions(game, bid):
    origin = bid - 720
    ids = [int(hid) for hid, h in catalog()['heroes'].items() if h['origin'] == origin][:2]
    assert len(ids) == 2
    seed_heroes(game, ids)
    assert send(game, 'BuildStarUP', bid=bid, kind=2).values['code'] == 10
    target = game[2].catalog.row(bid, 2, True)
    player = game[0].get(1)
    assert not game[3].upgrades.wonder_condition(target, player['snapshot'])
    seed_heroes(game, ids, star=3)
    assert game[3].upgrades.wonder_condition(target, game[0].get(1)['snapshot'])


def test_wonder_old_save_migration_preserves_progress_and_closed_wonder(game):
    repo = game[2]
    state = repo.load(1)
    state['wonders'] = state['wonders'][:7]
    state['wonders'][0].update(buildingLevel=7, buildingStar=2)
    repo.save(1, state)
    rows = list(map(BUILDING_BASE_INFO.decode, repo.growth_base(1)['civilization']))
    assert len(rows) == 8 and rows[0]['buildingLevel'] == 7 and rows[0]['buildingStar'] == 2
    assert rows[-1]['buildingId'] == 728 and rows[-1]['buildingLevel'] == 1
    assert send(game, 'BuildStarUP', bid=728, kind=2).values['code'] == 13
    assert len(repo.load(1)['wonders']) == 8


def test_wonder_unlock_funds_gate_and_transaction_rollback(game, monkeypatch):
    seed_heroes(game)
    store, _, repo, _, _ = game
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], level=24), player['revision'])
    assert send(game, 'BuildStarUP', bid=721, kind=2).values['code'] == 37
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], level=60), player['revision'])
    with store.db:
        store.db.execute('UPDATE inventory SET quantity=11 WHERE item_id=1237801')
    assert send(game, 'BuildStarUP', bid=721, kind=2).values['code'] == 22
    with store.db:
        store.db.execute('UPDATE inventory SET quantity=100 WHERE item_id=1237801')
    monkeypatch.setattr(repo, 'save', lambda *args: (_ for _ in ()).throw(RuntimeError('disk')))
    with pytest.raises(RuntimeError):
        send(game, 'BuildStarUP', bid=721, kind=2)
    assert quantity(store, 1237801) == 100
    assert repo.load(1)['wonders'][0].get('buildingStar', 0) == 0
    assert store.db.execute('SELECT count(*) FROM college_upgrade_receipts').fetchone()[0] == 0


@pytest.mark.parametrize('remaining,cost', [(3600, 11), (301, 1), (300, 0), (1, 0)])
def test_wonder_crystal_finish_native_free_period_and_replay(game, remaining, cost):
    store, clock, repo, service, _ = game
    state = repo.load(1)
    state['wonders'][0]['buildingStar'] = 1
    state['buildings'][0]['buildingLevel'] = 2
    repo.save(1, state)
    assert send(game, 'BuildingUpgrade', bid=721, kind=2).values['code'] == 10
    clock.value += 3600 - remaining
    if cost:
        assert send(game, 'BuildCrystalFinish', bid=721, kind=2, seq=2).values['code'] == 36
        assert repo.load(1)['wonder_queue'] is not None
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], crystal=100), player['revision'])
    result = send(game, 'BuildCrystalFinish', bid=721, kind=2, seq=2)
    assert result.values['code'] == 10 and result.values['buildStatus'] == 1
    assert result.values['crystal'] == 100 - cost
    assert store.get(1)['snapshot']['crystal'] == 100 - cost
    assert send(game, 'BuildCrystalFinish', bid=721, kind=2, seq=2).values == result.values
    assert store.get(1)['snapshot']['crystal'] == 100 - cost
    assert repo.load(1)['wonders'][0]['buildingLevel'] == 2
    assert send(game, 'BuildCrystalFinish', bid=721, kind=2, seq=3).values['code'] == 13
    assert service.upgrades.complete_due(1)[1].values['buildingId'] == 721
    assert service.upgrades.complete_due(1) == ()


def test_wonder_offline_bonus_settlement_never_commits_outer_transaction(game):
    store, clock, repo, service, _ = game
    state = repo.load(1)
    state['wonders'][0]['buildingStar'] = 1
    state['buildings'][0]['buildingLevel'] = 2
    repo.save(1, state)
    assert send(game, 'BuildingUpgrade', bid=721, kind=2).values['code'] == 10
    clock.value += 3600
    with pytest.raises(RuntimeError):
        with service.upgrades.economy.transaction():
            store.db.execute('UPDATE inventory SET quantity=quantity-1 WHERE item_id=1237801')
            assert other_attributes(store, 1, {'id': 1010}, clock) == {100: 71}
            raise RuntimeError('battle rollback')
    assert quantity(store, 1237801) == 95
    assert repo.load(1)['wonders'][0]['buildingLevel'] == 1
    assert repo.load(1)['wonder_queue'] is not None


def test_wonder_terminal_level_star_and_account_gate_never_charge(game):
    state = game[2].load(1)
    state['wonders'][0].update(buildingStar=6, buildingLevel=35)
    game[2].save(1, state)
    assert send(game, 'BuildStarUP', bid=721, kind=2).values['code'] == 14
    assert send(game, 'BuildingUpgrade', bid=721, kind=2).values['code'] == 14
    state['wonders'][0]['buildingLevel'] = 34
    game[2].save(1, state)
    assert send(game, 'BuildingUpgrade', bid=721, kind=2).values['code'] == 37
    assert quantity(game[0], 1237801) == 100
    assert game[0].db.execute('SELECT count(*) FROM college_upgrade_receipts').fetchone()[0] == 0

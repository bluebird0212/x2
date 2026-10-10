import asyncio
import pytest

from tests.unit.test_college_upgrade import game, quantity
from tests.unit.test_battle import packet
from x2server.messages.core import CORE_SCHEMAS
from x2server.messages.lobby import PRAY_QUEUE
from x2server.player.college_pray import PRAY_DAILY
from x2server.player.college import CollegeService
from x2server.player.login import LoginService


def setup(game):
    store, clock, repo, service, context = game
    p = store.get(1)
    p['snapshot']['heroes'] = [{'id': 1003, 'state': 2, 'level': 1, 'star': 1, 'exp': 0}]
    store.save_snapshot(1, p['snapshot'], p['revision'])
    state = repo.load(1)
    repo.catalog.state_row(state, 727)['buildingStar'] = 4
    repo.save(1, state)
    with store.db:
        for item in (1237840, 1201000):
            store.db.execute('INSERT INTO inventory VALUES (?,?,?)', (1, item, 20))
    return store, clock, repo, service, context


def send(game, flow, bid=727, seq=1, **fields):
    result = asyncio.run(game[3].dispatch(game[4], packet(
        {'buildingId': bid, **fields}, seq, 'C2L_' + flow)))
    for message in (*result.before_response, result, *result.pushes):
        CORE_SCHEMAS[message.message_name].encode(message.values)
    return result


def test_pray_start_speed_notifications_claim_replay_and_relogin(game):
    store, clock, repo, service, context = setup(game)
    result = send(game, 'BuildStartPrayGod', bid=727, heroId=1003, itemId=1201000)
    assert result.values['code'] == 10 and result.values['prayTime'] == 28800
    assert quantity(store, 1237840) == 19 and quantity(store, 1201000) == 19
    assert store.get(1)['snapshot']['gold'] == 497000
    assert store.get(1)['snapshot']['heroes'][0]['college_status'] == 1
    assert send(game, 'BuildStartPrayGod', bid=727, heroId=1003, itemId=1201000).values == result.values
    assert quantity(store, 1237840) == 19
    assert send(game, 'BuildRewardPrayGod', bid=727, seq=2).values['code'] == 205
    hero = store.get(1)['snapshot']['heroes'][0]
    assert service.jobs.heroes(repo.load(1), store.get(1)['snapshot'], [hero['id']])[0] == 62
    game = (*game[:3], CollegeService(repo, economy=service.prayers.economy), context)
    assert PRAY_QUEUE.decode(repo.growth_base(1)['prayQueue'][0])['prayHeroID'] == 1003
    daily = LoginService.snapshot_push(store.get(1), store, clock.now()).values['Daily']
    assert PRAY_DAILY.decode(daily)['PrayCount'] == 1
    speed = send(game, 'BuildQuickenPrayGod', bid=727, seq=3, itemId=1237832, itemNum=8)
    assert speed.values['code'] == 10 and speed.values['endTime'] == clock.now()
    assert quantity(store, 1237832) == 92
    assert send(game, 'BuildQuickenPrayGod', bid=727, seq=3, itemId=1237832, itemNum=8).values == speed.values
    messages = game[3].upgrades.complete_due(1)
    assert [m.message_name for m in messages] == ['L2C_QueryGrowthBase', 'L2C_PrayEnd']
    assert game[3].upgrades.complete_due(1) == ()
    assert PRAY_QUEUE.decode(repo.growth_base(1)['prayQueue'][0])['prayStatus'] == 2
    claim = send(game, 'BuildRewardPrayGod', bid=727, seq=4)
    # Native L2C_BuildRewardPrayGod.Serialize 0x3afaa58 writes tag 0x22.
    from x2server.messages.college import COLLEGE_SCHEMAS
    assert COLLEGE_SCHEMAS['L2C_BuildRewardPrayGod'].encode({'rewardData': b'\x08\x0a'}) == b'\x22\x02\x08\x0a'
    assert claim.values['code'] == 10 and quantity(store, 1201003) == 10
    assert send(game, 'BuildRewardPrayGod', bid=727, seq=4).values == claim.values
    assert send(game, 'BuildRewardPrayGod', bid=727, seq=5).values['code'] == 13
    assert quantity(store, 1201003) == 10 and not repo.load(1)['pray']
    assert store.get(1)['snapshot']['heroes'][0]['college_status'] == 0
    queues = {r['buildingId']: r for r in map(PRAY_QUEUE.decode, claim.before_response[0].values['prayQueue'])}
    assert set(queues) == set(range(721, 729))
    assert queues[727]['prayStatus'] == 0 and queues[727]['prayHeroID'] == 0
    assert all(r['prayEndTime'] == 0 for r in queues.values())
    assert PRAY_QUEUE.decode(next(r for r in repo.growth_base(1)['prayQueue']
                                 if PRAY_QUEUE.decode(r)['buildingId'] == 727))['prayStatus'] == 0


def test_pray_cancel_and_daily_reset(game):
    store, clock, repo, service, context = setup(game)
    for n in range(5):
        assert send(game, 'BuildStartPrayGod', bid=727, seq=n*2+1, heroId=1003).values['code'] == 10
        assert send(game, 'BuildCancelPrayGod', bid=727, seq=n*2+2).values['code'] == 10
    assert store.get(1)['snapshot']['gold'] == 485000
    assert quantity(store, 1237840) == 20
    assert send(game, 'BuildStartPrayGod', bid=727, seq=11, heroId=1003).values['code'] == 13
    clock.value += 86400
    assert send(game, 'BuildStartPrayGod', bid=727, seq=12, heroId=1003).values['code'] == 10


@pytest.mark.parametrize('invalid', ['locked','foreign_origin','unowned','occupied','no_items','bad_sacrifice'])
def test_pray_admission_failures_do_not_consume(game, invalid):
    store, clock, repo, service, context = setup(game)
    fields = dict(heroId=1003)
    bid = 727
    if invalid == 'locked':
        state = repo.load(1)
        repo.catalog.state_row(state, bid)['buildingStar'] = 1
        repo.save(1, state)
    elif invalid == 'foreign_origin':
        bid = 721
        state = repo.load(1)
        repo.catalog.state_row(state, bid)['buildingStar'] = 2
        repo.save(1, state)
    elif invalid == 'unowned':
        fields['heroId'] = 999999
    elif invalid == 'occupied':
        p = store.get(1)
        p['snapshot']['heroes'][0]['college_status'] = 3
        store.save_snapshot(1, p['snapshot'], p['revision'])
    elif invalid == 'no_items':
        with store.db:
            store.db.execute('UPDATE inventory SET quantity=0 WHERE item_id=1237840')
    else:
        fields['itemId'] = 1237901
    gold = store.get(1)['snapshot']['gold']
    count = quantity(store, 1237840)
    assert send(game, 'BuildStartPrayGod', bid=bid, **fields).values['code'] != 10
    assert store.get(1)['snapshot']['gold'] == gold and quantity(store, 1237840) == count
    assert not repo.load(1)['pray']


def test_prayer_star_gates_without_guardian_and_offline_claim(game):
    store, clock, repo, service, _ = setup(game)
    state = repo.load(1)
    wonder = repo.catalog.state_row(state, 727)
    wonder['buildingStar'] = 1
    repo.save(1, state)
    assert send(game, 'BuildStartPrayGod').values['code'] == 57
    wonder['buildingStar'] = 2
    repo.save(1, state)
    assert send(game, 'BuildStartPrayGod', seq=2, heroId=1003).values['code'] == 57
    assert send(game, 'BuildStartPrayGod', seq=3, itemId=1201000).values['code'] == 57
    assert send(game, 'BuildStartPrayGod', seq=4).values['code'] == 10
    job = repo.load(1)['pray'][0]
    assert service.prayers.heroes[next(h for h,r in service.prayers.heroes.items()
        if r.get('ChipPropID') == job['reward_item'])]['Origin']['value'] == 7
    assert store.get(1)['snapshot']['heroes'][0].get('college_status', 0) == 0
    clock.value += 28801
    assert send(game, 'BuildRewardPrayGod', seq=5).values['code'] == 10
    assert quantity(store, job['reward_item']) == 5


def test_prayer_save_failures_rollback_wallet_chip_hero_queue_and_receipt(game, monkeypatch):
    store, clock, repo, _, _ = setup(game)
    original = repo.save
    def fail(*args):
        raise RuntimeError('disk failure')
    monkeypatch.setattr(repo, 'save', fail)
    with pytest.raises(RuntimeError):
        send(game, 'BuildStartPrayGod', heroId=1003, itemId=1201000)
    assert store.get(1)['snapshot']['gold'] == 500000
    assert quantity(store, 1201000) == quantity(store, 1237840) == 20
    assert not repo.load(1)['pray']
    assert not store.get(1)['snapshot']['heroes'][0].get('college_status')
    assert store.db.execute('SELECT count(*) FROM college_pray_receipts').fetchone()[0] == 0
    monkeypatch.setattr(repo, 'save', original)
    send(game, 'BuildStartPrayGod', heroId=1003)
    clock.value += 28800
    monkeypatch.setattr(repo, 'save', fail)
    with pytest.raises(RuntimeError):
        send(game, 'BuildRewardPrayGod', seq=2)
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1201003').fetchone() is None
    assert repo.load(1)['pray']
    assert store.get(1)['snapshot']['heroes'][0]['college_status'] == 1
    assert store.db.execute('SELECT count(*) FROM college_pray_receipts').fetchone()[0] == 1


def test_prayer_daily_resets_at_five_am_not_midnight():
    from x2server.player.college_pray import prayer_day, daily_fields
    # 2023-11-15 04:59:59 and 05:00:00 in Asia/Shanghai.
    from datetime import datetime, timezone, timedelta
    after = int(datetime(2023, 11, 15, 5, tzinfo=timezone(timedelta(hours=8))).timestamp())
    before = after - 1
    state = {'pray_daily': {'day': prayer_day(before), 'count': 5}}
    assert PRAY_DAILY.decode(daily_fields(state, before))['PrayCount'] == 5
    assert PRAY_DAILY.decode(daily_fields(state, after))['PrayCount'] == 0


def test_online_daily_reset_pushes_once_and_cancel_keeps_speed_consumed(game):
    store, clock, repo, service, _ = setup(game)
    assert send(game, 'BuildStartPrayGod', heroId=1003, itemId=1201000).values['code'] == 10
    assert send(game, 'BuildQuickenPrayGod', seq=2, itemId=1237832, itemNum=1).values['code'] == 10
    assert send(game, 'BuildCancelPrayGod', seq=3).values['code'] == 10
    assert quantity(store, 1237832) == 99 and quantity(store, 1237840) == 20
    assert quantity(store, 1201000) == 19 and store.get(1)['snapshot']['gold'] == 497000
    clock.value += 86400
    pushes = service.upgrades.complete_due(1)
    assert [m.message_name for m in pushes] == ['PlayerDataProto']
    assert PRAY_DAILY.decode(pushes[0].values['Daily'])['PrayCount'] == 0
    assert service.upgrades.complete_due(1) == ()

import copy
import math
import pytest

from tests.unit.test_college_upgrade import game, quantity
from tests.unit.test_college_alchemy import send
from x2server.messages.lobby import CUSTOMER_INFO
from x2server.messages.favor import FAVOR_CHANGE_INFO
from x2server.player.college import CollegeService, CollegeStateRepository
from x2server.player.economy import EconomyService
from x2server.player.store import PlayerStore


def setup_order(game, pos=0, energy=200):
    store, clock, repo, service, context = game
    repo.growth_base(1)
    customer = service._customer_for(1, pos)
    meta = next(r for r in service._load_catalog()['customers'] if r['sellQuestId'] == customer['questId'])
    player = store.get(1)
    player['snapshot']['heroes'] = [{'id': meta['heroId'], 'state': 2, 'level': 1,
        'star': 1, 'favor': {'level': 1, 'exp': 0}}]
    store.save_snapshot(1, player['snapshot'], player['revision'])
    state = repo.load(1)
    state['star_energy'] = energy
    repo.save(1, state)
    with store.db:
        for item in (*customer['itemId'], customer['adviseItemId']):
            store.db.execute('INSERT OR REPLACE INTO inventory VALUES (?,?,?)', (1, item, 10))
    recipe = next(r for r in service.alchemy.recipes.values() if r['ProductID'] == customer['itemId'][0])
    return customer, recipe


@pytest.mark.parametrize('mode', ['plusPrice', 'discountPrice'])
def test_negotiated_trade_price_energy_favor_and_replay(game, mode):
    customer, recipe = setup_order(game)
    store, _, repo, service, _ = game
    price = recipe['Gold']
    before = store.get(1)['snapshot']
    response = send(game, 'AlchemyFinish', type=1, posIndex=0, **{mode: True})
    assert response.values['code'] == 10
    expected_gold = price * 2 if mode == 'plusPrice' else price // 2
    assert store.get(1)['snapshot']['gold'] == before['gold'] + expected_gold
    assert quantity(store, customer['itemId'][0]) == 9
    assert repo.load(1)['star_energy'] == (200 - math.ceil(price / 5000 * 15) if mode == 'plusPrice' else 200)
    favor = store.get(1)['snapshot']['heroes'][0]['favor']
    assert favor['exp'] == (math.ceil(price / 5000 * 5) if mode == 'discountPrice' else 0)
    if mode == 'discountPrice':
        change = next(m for m in response.pushes if m.message_name == 'L2C_FavorChangeInfo')
        assert FAVOR_CHANGE_INFO.decode(change.values['data'][0])['type'] == 13
        assert any(m.message_name == 'PlayerDataProto' for m in response.pushes)
    saved = store.get(1)['snapshot']
    assert send(game, 'AlchemyFinish', type=1, posIndex=0, **{mode: True}).values == response.values
    assert store.get(1)['snapshot'] == saved and quantity(store, customer['itemId'][0]) == 9


def test_suggestion_query_restart_trade_discount_and_refusal(game):
    customer, _ = setup_order(game)
    store, clock, repo, service, context = game
    recommended = customer['adviseItemId']
    recipe = next(r for r in service.alchemy.recipes.values() if r['ProductID'] == recommended)
    response = send(game, 'AlchemyButtonClick', type=1, posIndex=0)
    assert response.values == {'code': 10, 'type': 1, 'posIndex': 0, 'result': customer['itemId'][0], 'param': 0}
    assert repo.load(1)['star_energy'] == 200 - math.ceil(recipe['Gold'] / 10000 * 2)
    assert send(game, 'AlchemyButtonClick', type=1, posIndex=0).values == response.values
    queried = send(game, 'SingleCustomerInfo', seq=2, posIndex=0)
    changed = CUSTOMER_INFO.decode(queried.values['customere'])
    assert changed['itemId'] == [recommended] and changed['adviseItemId'] == customer['itemId'][0]
    assert quantity(store, recommended) == 10  # suggestion itself does not sell
    assert send(game, 'AlchemyButtonClick', seq=3, type=2, posIndex=0).values['code'] == 13
    restored = PlayerStore(store.path)
    rebuilt = CollegeService(CollegeStateRepository(restored, clock), economy=EconomyService(restored, clock.now))
    assert rebuilt._customer_for(1, 0) == changed
    restored.close()
    before_gold = store.get(1)['snapshot']['gold']
    trade = send(game, 'AlchemyFinish', seq=4, type=1, posIndex=0, discountPrice=True)
    assert trade.values['code'] == 10
    assert quantity(store, recommended) == 9 and quantity(store, customer['itemId'][0]) == 10
    assert store.get(1)['snapshot']['gold'] == before_gold + recipe['Gold'] // 2
    assert store.get(1)['snapshot']['heroes'][0]['favor']['exp'] == math.ceil(recipe['Gold'] / 5000 * 5)
    assert send(game, 'AlchemyFinish', seq=5, type=2, posIndex=0).values['code'] == 10
    assert '0' not in repo.load(1)['alchemy']['customer_orders']
    assert service._customer_for(1, 0)['adviseItemId'] != 0


@pytest.mark.parametrize('flow,fields', [('AlchemyButtonClick', {'type': 1}),
    ('AlchemyFinish', {'type': 1, 'plusPrice': True}),
    ('AlchemyFinish', {'type': 1, 'discountPrice': True})])
def test_customer_disk_failure_rolls_back_all_ledgers(game, monkeypatch, flow, fields):
    customer, _ = setup_order(game)
    store, _, repo, _, _ = game
    before = store.get(1)['snapshot']
    state = copy.deepcopy(repo.load(1))
    monkeypatch.setattr(repo, 'save', lambda *args: (_ for _ in ()).throw(RuntimeError('disk')))
    with pytest.raises(RuntimeError):
        send(game, flow, posIndex=0, **fields)
    assert store.get(1)['snapshot'] == before and repo.load(1) == state
    assert quantity(store, customer['itemId'][0]) == 10
    assert store.db.execute('SELECT count(*) FROM college_alchemy_receipts').fetchone()[0] == 0


def test_insufficient_energy_goods_and_unowned_favor(game):
    customer, _ = setup_order(game, energy=0)
    for seq, flow in enumerate(('AlchemyButtonClick', 'AlchemyFinish'), 1):
        result = send(game, flow, seq=seq, type=1, posIndex=0, **({'plusPrice': True} if seq == 2 else {}))
        assert result.values['code'] == 38
    store = game[0]
    with store.db:
        store.db.execute('UPDATE inventory SET quantity=0 WHERE player_id=1 AND item_id=?', (customer['itemId'][0],))
    before = store.get(1)['snapshot']
    assert send(game, 'AlchemyFinish', seq=3, type=1, posIndex=0, discountPrice=True).values['code'] == 22
    assert store.get(1)['snapshot'] == before


def test_discount_respects_favor_breakthrough(game):
    setup_order(game)
    store, _, _, service, _ = game
    from x2server.player.favor import catalog
    data = catalog()
    level = next(r['FavorLevel'] for r in data['favorabilitylevel'] if r.get('IsBreak'))
    player = store.get(1)
    player['snapshot']['heroes'][0]['favor'] = {'level': level, 'exp': 100000}
    store.save_snapshot(1, player['snapshot'], player['revision'])
    assert send(game, 'AlchemyFinish', type=1, posIndex=0, discountPrice=True).values['code'] == 10
    favor = store.get(1)['snapshot']['heroes'][0]['favor']
    assert favor['level'] == level and favor['exp'] > 100000

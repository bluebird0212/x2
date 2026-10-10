import asyncio
import json
import pytest

from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from x2server.messages.equip_plan import EQUIP_PLAN, PLAN, PLAN_ENTRY, PLAN_POS
from x2server.messages.equipment import HERO_EQUIP
from x2server.player.equipment import EquipmentService
from x2server.player.equip_plans import EquipPlanService, snapshot_value, MAX_PLAN_ID
from x2server.player.store import PlayerStore
from x2server.player.economy import EconomyService


@pytest.fixture
def plans(env):
    store, economy, ctx = env
    equipment = EquipmentService(store, economy)
    service = EquipPlanService(store, economy, equipment)
    ids = []
    with store.db:
        for part in (1, 2):
            ids.append(store.db.execute(
                "INSERT INTO equipment_instances (player_id,type_id,star,level,param,marker) VALUES (1,?,3,0,'{}',?)",
                (1240000 + part, 'plan-test-' + str(part))).lastrowid)
    return store, economy, ctx, equipment, service, ids


def send(plans, name, values, rid=1):
    return asyncio.run(plans[4].handle(plans[2], packet(values, name=name, request_id=rid)))


def positions(ids):
    return [PLAN_POS.encode({'Key':slot,'Value':eid}) for slot, eid in enumerate(ids)]


def test_full_plan_save_top_use_delete_and_replay(plans):
    store, _, _, _, service, ids = plans
    values = {'name':'test','pos':positions(ids)}
    created = send(plans, 'C2L_UpdateEquipPlan', values)
    pid = created.values['planId']
    assert created.values['code'] == 10
    assert created.before_response[0].message_name == 'PlayerDataProto'
    assert send(plans, 'C2L_UpdateEquipPlan', values).values == created.values
    assert len(store.get(1)['snapshot']['equip_plans']['plans']) == 1
    assert send(plans, 'C2L_SetTopEquipPlan', {'planId':pid,'isTop':True}, 2).values['code'] == 10
    assert store.get(1)['snapshot']['equip_plans']['plans'][str(pid)]['set_top_time'] > 0
    used = send(plans, 'C2L_UseEquipPlan', {'planId':pid,'heroId':1003}, 3)
    assert used.values['code'] == 10
    assert {e['equip_id'] for e in store.get(1)['snapshot']['heroes'][0]['equips']} == set(ids)
    assert used.before_response[0].message_name == 'L2C_HeroUpdate'
    assert send(plans, 'C2L_DelEquipPlan', {'planId':pid}, 4).values['code'] == 10
    wire = EQUIP_PLAN.decode(snapshot_value(store.get(1)['snapshot']))['Plan']
    tombstone = next(PLAN_ENTRY.decode(raw) for raw in wire if PLAN_ENTRY.decode(raw)['Key'] == pid)
    assert 'Val' not in tombstone
    # Old creation must not resurrect a deleted preset.
    assert send(plans, 'C2L_UpdateEquipPlan', values).values == created.values
    assert not store.get(1)['snapshot']['equip_plans']['plans']


def test_removed_slots_use_native_incremental_tombstones(plans):
    store, _, _, _, _, ids = plans
    send(plans, 'C2L_UpdateEquipPlan', {'planId':1,'name':'two','pos':positions(ids)})
    send(plans, 'C2L_UpdateEquipPlan', {'planId':1,'name':'one','pos':positions(ids[:1])}, 2)
    entry = PLAN_ENTRY.decode(EQUIP_PLAN.decode(snapshot_value(store.get(1)['snapshot']))['Plan'][0])
    rows = [PLAN_POS.decode(raw) for raw in PLAN.decode(entry['Val'])['Position']]
    client = {0:ids[0],1:ids[1]}
    for row in rows:
        if 'Value' in row:
            client[row['Key']] = row['Value']
        else:
            client.pop(row['Key'],None)
    assert client == {0:ids[0]}
    assert len(rows) == 6


def test_ids_do_not_overwrite_and_exhaustion_refuses(plans):
    store, _, _, _, _, _ = plans
    send(plans, 'C2L_UpdateEquipPlan', {'planId':1,'name':'first'})
    assert send(plans, 'C2L_UpdateEquipPlan', {'name':'second'}, 2).values['planId'] == 2
    assert len(store.get(1)['snapshot']['equip_plans']['plans']) == 2
    player = store.get(1)
    player['snapshot']['equip_plans']['next_id'] = MAX_PLAN_ID
    store.save_snapshot(1, player['snapshot'], player['revision'])
    before = store.get(1)
    assert send(plans, 'C2L_UpdateEquipPlan', {'name':'overflow'}, 3).values['code'] == 13
    assert store.get(1) == before


@pytest.mark.parametrize('bad', [positions([999999]), [PLAN_POS.encode({'Key':6,'Value':1})],
    [PLAN_POS.encode({'Key':0,'Value':1}),PLAN_POS.encode({'Key':1,'Value':1})],
    [PLAN_POS.encode({'Key':0,'Value':2})]])
def test_save_invalid_equipment_refuses_without_changes(plans,bad):
    before = plans[0].get(1)
    assert send(plans, 'C2L_UpdateEquipPlan', {'name':'bad','pos':bad}).values['code'] == 13
    assert plans[0].get(1) == before


def test_decomposed_or_mismatched_piece_rejects_whole_loadout(plans):
    store, _, _, _, _, ids = plans
    send(plans, 'C2L_UpdateEquipPlan', {'planId':1,'pos':positions(ids)})
    with store.db:
        store.db.execute('DELETE FROM equipment_instances WHERE id=?',(ids[1],))
    before = store.get(1)
    assert send(plans, 'C2L_UseEquipPlan', {'planId':1,'heroId':1003}, 2).values['code'] == 13
    assert store.get(1) == before


def test_plan_receipt_failure_rolls_back_snapshot(plans):
    store = plans[0]
    with store.db:
        store.db.execute("CREATE TRIGGER refuse_plan_receipt BEFORE INSERT ON equip_plan_receipts BEGIN SELECT RAISE(ABORT,'test'); END")
    before = store.get(1)
    assert send(plans, 'C2L_UpdateEquipPlan', {'name':'rollback'}).values['code'] == 13
    assert store.get(1) == before


def test_lock_replay_restart_and_reclaim_protection(plans):
    store, economy, ctx, equipment, _, ids = plans
    req = packet({'equipID':ids[0]},name='C2L_LockEquip',request_id=100)
    first = asyncio.run(equipment.lock(ctx,req))
    assert HERO_EQUIP.decode(first.values['heroEquip'])['lockState'] == 1
    equipment = EquipmentService(store,economy)
    assert asyncio.run(equipment.lock(ctx,req)).values == first.values
    assert store.db.execute('SELECT locked FROM equipment_instances WHERE id=?',(ids[0],)).fetchone()[0] == 1
    before = store.get(1)
    result = asyncio.run(equipment.reclaim(ctx,packet({'equipID':ids},name='C2L_EquipReclaim')))
    assert result.values['code'] == 13
    assert store.get(1) == before
    assert store.db.execute('SELECT COUNT(*) FROM equipment_instances').fetchone()[0] == 2
    unlocked = asyncio.run(equipment.lock(ctx,packet({'equipID':ids[0]},name='C2L_LockEquip',request_id=101)))
    assert HERO_EQUIP.decode(unlocked.values['heroEquip'])['lockState'] == 0
    # A late replay of the first lock must neither re-lock nor show stale state.
    replay = asyncio.run(equipment.lock(ctx,req))
    assert HERO_EQUIP.decode(replay.values['heroEquip'])['lockState'] == 0


def test_lock_receipt_failure_rolls_back_lock_state(plans):
    store, _, ctx, equipment, _, ids = plans
    with store.db:
        store.db.execute("CREATE TRIGGER refuse_lock_receipt BEFORE INSERT ON equipment_lock_receipts BEGIN SELECT RAISE(ABORT,'test'); END")
    result = asyncio.run(equipment.lock(ctx,packet(
        {'equipID':ids[0]},name='C2L_LockEquip',request_id=301)))
    assert result.values['code'] == 13
    assert store.db.execute('SELECT locked FROM equipment_instances WHERE id=?',(ids[0],)).fetchone()[0] == 0


def test_saved_empty_slots_unequip_previous_target_pieces(plans):
    store, _, _, _, _, ids = plans
    send(plans, 'C2L_UpdateEquipPlan', {'planId':1,'pos':positions(ids[:1])})
    player = store.get(1)
    player['snapshot']['heroes'][0]['equips'] = [{'position':1,'equip_id':ids[1]}]
    store.save_snapshot(1,player['snapshot'],player['revision'])
    assert send(plans,'C2L_UseEquipPlan',{'planId':1,'heroId':1003},2).values['code'] == 10
    assert store.get(1)['snapshot']['heroes'][0]['equips'] == [{'position':0,'equip_id':ids[0]}]


def test_old_equipment_schema_migration_preserves_instances(tmp_path):
    store = PlayerStore(tmp_path/'old-equipment.db')
    store.login('old',1,0)
    with store.db:
        store.db.execute('''CREATE TABLE equipment_instances (
            id INTEGER PRIMARY KEY,player_id INTEGER,type_id INTEGER,level INTEGER,
            exp INTEGER,star INTEGER,param TEXT,marker TEXT)''')
        store.db.execute("INSERT INTO equipment_instances VALUES (55,1,1240001,0,0,3,'{}','old')")
    try:
        equipment = EquipmentService(store)
        row = store.db.execute('SELECT id,type_id,star,marker,locked FROM equipment_instances').fetchone()
        assert tuple(row) == (55,1240001,3,'old',0)
        assert HERO_EQUIP.decode(equipment.values(1)['equip'][0])['lockState'] == 0
    finally:
        store.close()


def test_preset_and_receipt_survive_database_reopen(plans):
    store, _, ctx, _, _, ids = plans
    values = {'name':'durable','pos':positions(ids)}
    first = send(plans,'C2L_UpdateEquipPlan',values)
    reopened = PlayerStore(store.path)
    try:
        economy = EconomyService(reopened)
        service = EquipPlanService(reopened,economy,EquipmentService(reopened,economy))
        replay = asyncio.run(service.handle(ctx,packet(values,name='C2L_UpdateEquipPlan')))
        assert replay.values == first.values
        assert len(reopened.get(1)['snapshot']['equip_plans']['plans']) == 1
    finally:
        reopened.close()


def test_unknown_delete_refuses_and_repeat_known_delete_is_idempotent(plans):
    store = plans[0]
    before = store.get(1)
    assert send(plans,'C2L_DelEquipPlan',{'planId':60000}).values['code'] == 13
    assert store.get(1) == before
    send(plans,'C2L_UpdateEquipPlan',{'planId':1,'name':'delete'},2)
    assert send(plans,'C2L_DelEquipPlan',{'planId':1},3).values['code'] == 10
    before = store.get(1)
    assert send(plans,'C2L_DelEquipPlan',{'planId':1},4).values['code'] == 10
    assert store.get(1) == before

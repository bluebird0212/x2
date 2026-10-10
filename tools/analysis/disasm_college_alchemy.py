"""Capture 2.4 production, element simulation and speed-card gate consumers."""
import json
import sys
from pathlib import Path

sys.path.insert(0, 'D:/demo/x2/.phase3_deps')
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

root = Path('D:/demo/x2')
methods = json.loads((root / 'tools/Il2CppDumper-bin/script.json').read_text())['ScriptMethod']
names = {m['Address']: m['Name'] for m in methods}
binary = (root / 'apk/lib/arm64-v8a/libil2cpp.so').read_bytes()
decoder = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
selected = [m for m in methods if
    ('CollegeModule$$' in m['Name'] and any(s in m['Name'] for s in (
        'OnGetHelpPowerSpeedVaild', 'SendBuildCanSpeed', 'SpecialDataFormat',
        'GetElementStorage', 'GetFurnaceRecipe', 'GetLockCount', 'GetMainHallNum')))
    or ('CollegeAlchemyModule' in m['Name'] and any(s in m['Name'] for s in (
        'SendMakeItem', 'OnReceiveMakeItem', 'GetRecipeCost', 'GetRecipeTime',
        'GetRecipeSell', 'OnReceiveAlchemyCollect', 'CheckRecipeUpgrade',
        'ResetElementSimulation', 'GetElementNum', 'ProductionPosition',
        'GetProductionBarState', 'OnReceiveMakIngSpeed', 'OnReceiveCancel',
        'OnReceiveOnekey', 'OnReceiveOneKey', 'GetProductionBarMax',
        'RefreshRecipeMaxUnlock', '.cctor', 'GetExpPhase', 'FindEffectInRecipeLevel',
        'OnReceiveAlchemyMainData', 'OnReceiveAlchemyMakeCancel', 'OnReceiveAlchemyOnekeyCollect',
        'InitData', 'OnReceiveMakeCancle', 'OnReceiveOnceGet', 'CheckMakingMaterialLack', 'RecoverCycle')))
    or ('CollegeFurnaceComposeTab$$' in m['Name'] and any(s in m['Name'] for s in ('Refresh', 'Cancel')))]
addresses = sorted(names)
out = []
for method in selected:
    start = method['Address']
    end = next((v for v in addresses if v > start), start + 1024)
    out.append(f"\n===== {method['Name']} @ {start:#x} =====")
    for ins in decoder.disasm(binary[start:end], start):
        label = ''
        if ins.mnemonic in ('bl', 'b') and ins.op_str.startswith('#0x'):
            label = ' ; ' + names.get(int(ins.op_str[1:], 16), '')
        out.append(f'{ins.address:09x}: {ins.mnemonic:8} {ins.op_str}{label}')
Path('runtime/college_alchemy_disasm.txt').write_text('\n'.join(out), encoding='utf8')
print('Captured', len(selected), 'methods')

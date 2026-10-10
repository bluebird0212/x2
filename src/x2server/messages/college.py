"""College (白夜行星) wire schemas beyond the entry queries in messages/lobby.py.

Field numbers follow native Serialize methods; declaration order alone is not
reliable (C2L_StartTrain.heroId is field 4, with fields 2/3 reserved). Response
schemas carry the full declared field sets even where Revival currently only
answers with an error code, so later phases can fill them without reshaping.
"""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema

COLLEGE_IDS = (
    ("BuildingUpgrade", 233, 244), ("BuildSpeedUP", 234, 245), ("BuildStarUP", 235, 246),
    ("BuildCrystalFinish", 271, 272), ("ExchangePower", 238, 249),
    ("StartExplore", 242, 253), ("CancelExplore", 236, 247), ("ExploreSpeed", 624, 625),
    ("FinishExplore", 239, 250),
    ("StartTrain", 259, 262), ("CancelTrain", 257, 260), ("FinishTrain", 258, 261),
    ("BuildStartPrayGod", 369, 373), ("BuildCancelPrayGod", 366, 370),
    ("BuildRewardPrayGod", 368, 372), ("BuildQuickenPrayGod", 367, 371),
    ("AlchemyMainData", 590, 591), ("SingleCustomerInfo", 592, 593), ("MakeItem", 594, 595), ("MakIngSpeed", 596, 597),
    ("AlchemyFinish", 598, 599), ("AlchemyButtonClick", 600, 601), ("AlchemyCollect", 602, 603),
    ("AlchemyBuy", 604, 605), ("AlchemyMakeCancel", 824, 825),
    ("AlchemyOnekeyCollect", 826, 827),
    ("WashingRoomRandomAttri", 1055, 1056), ("WashingRoomOpt", 1057, 1058),
    ("SetAssistHero", 606, 607), ("QueryFirstReCharge", 633, 634),
    ("QueryAccumulateReCharge", 637, 638), ("HelpPowerSpeed", 879, 880),
    ("HelpPowerSpeedValid", 881, 882),
)

EQUIP_PARAM = ProtoSchema("EquipParam", (
    F(1, "At1", K.INT32), F(2, "Av1", K.INT32), F(3, "At2", K.INT32), F(4, "Av2", K.INT32),
    F(5, "At3", K.INT32), F(6, "Av3", K.INT32), F(7, "At4", K.INT32), F(8, "Av4", K.INT32),
    F(9, "At5", K.INT32), F(10, "Av5", K.INT32), F(11, "At6", K.INT32), F(12, "Av6", K.INT32),
    F(13, "Lock1", K.INT32), F(14, "Lock2", K.INT32), F(15, "Lock3", K.INT32),
    F(16, "Lock4", K.INT32), F(17, "Lock5", K.INT32), F(18, "Lock6", K.INT32)))
HELP_POWER_SPEED_PARAM = ProtoSchema("HelpPowerSpeedParam", (
    F(1, "playerIded", K.INT64), F(2, "buildingId", K.INT32), F(3, "buildingLevel", K.INT32)))
ACCUMULATE_RECHARGE_DATA = ProtoSchema("AccumulateReChargeData", (
    F(1, "accumulateReChargeId", K.INT32), F(2, "state", K.INT32)))
ALCHEMY_RECIPE_BAR_DATA = ProtoSchema('AlchemyRecipeBarData', (
    F(1, 'recipeId', K.INT32), F(2, 'expBefore', K.INT32), F(3, 'exp', K.INT32),
    F(4, 'posIndex', K.INT32, repeated=True)))

_C2L_FIELDS = {
    "BuildingUpgrade": (F(1, "buildingId", K.INT32), F(2, "type", K.ENUM)),
    "BuildSpeedUP": (F(1, "buildingId", K.INT32), F(2, "type", K.ENUM),
                     F(3, "itemId", K.INT32), F(4, "itemNum", K.INT32)),
    "BuildStarUP": (F(1, "buildingId", K.INT32), F(2, "type", K.ENUM)),
    "BuildCrystalFinish": (F(1, "buildingId", K.INT32), F(2, "type", K.ENUM)),
    "ExchangePower": (F(1, "power", K.INT32),),
    "StartExplore": (F(1, "exploreId", K.INT32), F(2, "diffdifficulty", K.INT32),
                     F(3, "heroIds", K.INT32, repeated=True), F(4, "ruinId", K.INT32)),
    "CancelExplore": (F(1, "exploreId", K.INT32),),
    "ExploreSpeed": (F(1, "exploreId", K.INT32),),
    "FinishExplore": (F(1, "exploreId", K.INT32),),
    "StartTrain": (F(1, "trainId", K.INT32), F(4, "heroId", K.INT32)),
    "CancelTrain": (F(1, "trainId", K.INT32),),
    "FinishTrain": (F(1, "trainId", K.INT32),),
    "BuildStartPrayGod": (F(1, "buildingId", K.INT32), F(2, "heroId", K.INT32),
                          F(3, "itemId", K.INT32)),
    "BuildCancelPrayGod": (F(1, "buildingId", K.INT32),),
    "BuildRewardPrayGod": (F(1, "buildingId", K.INT32),),
    "BuildQuickenPrayGod": (F(1, "buildingId", K.INT32), F(2, "itemId", K.INT32),
                            F(3, "itemNum", K.INT32)),
    "SingleCustomerInfo": (F(1, "posIndex", K.INT32),),
    "AlchemyMainData": (),
    "MakeItem": (F(1, "posIndex", K.INT32), F(2, "recipeId", K.INT32)),
    "MakIngSpeed": (F(1, "posIndex", K.INT32), F(2, "type", K.INT32)),
    "AlchemyFinish": (F(1, "type", K.INT32), F(2, "posIndex", K.INT32),
                      F(3, "plusPrice", K.BOOL), F(4, "discountPrice", K.BOOL)),
    "AlchemyButtonClick": (F(1, "type", K.INT32), F(2, "posIndex", K.INT32)),
    "AlchemyCollect": (F(1, "posIndex", K.INT32),),
    "AlchemyBuy": (F(1, "type", K.INT32), F(2, "typeId", K.INT32)),
    "AlchemyMakeCancel": (F(1, "posIndex", K.INT32),),
    "AlchemyOnekeyCollect": (F(1, "posIndex", K.INT32, repeated=True),),
    "WashingRoomRandomAttri": (F(1, "equipID", K.INT32),),
    "WashingRoomOpt": (F(1, "equipID", K.INT32), F(2, "opt", K.INT32),
                       F(3, "equipParam", K.MESSAGE)),
    "SetAssistHero": (F(1, "heroID", K.INT32), F(2, "optType", K.INT32)),
    "QueryFirstReCharge": (),
    "QueryAccumulateReCharge": (),
    "HelpPowerSpeed": (F(1, "helpPowerSpeedParam", K.MESSAGE, repeated=True),
                       F(2, "helpPower", K.INT32)),
    "HelpPowerSpeedValid": (F(1, "type", K.INT32),),
}

_L2C_FIELDS = {
    "BuildingUpgrade": (F(1, "code", K.ENUM), F(2, "buildingId", K.INT32),
                        F(3, "type", K.ENUM), F(4, "endTime", K.INT32),
                        F(5, "buildTime", K.INT32)),
    "BuildSpeedUP": (F(1, "code", K.ENUM), F(2, "buildingId", K.INT32), F(3, "type", K.ENUM),
                     F(4, "endTime", K.INT32), F(5, "buildTime", K.INT32),
                     F(6, "itemId", K.INT32), F(7, "itemNum", K.INT32),
                     F(8, "buildStatus", K.INT32)),
    "BuildStarUP": (F(1, "code", K.ENUM), F(2, "buildingId", K.INT32), F(3, "type", K.ENUM),
                    F(4, "star", K.INT32)),
    "BuildCrystalFinish": (F(1, "code", K.ENUM), F(2, "buildingId", K.INT32),
                           F(3, "type", K.ENUM), F(4, "buildStatus", K.INT32),
                           F(5, "crystal", K.INT32)),
    "ExchangePower": (F(1, "code", K.ENUM), F(2, "power", K.INT32), F(3, "extraPower", K.INT32)),
    "StartExplore": (F(1, "code", K.ENUM),),
    "CancelExplore": (F(1, "code", K.ENUM), F(2, "exploreId", K.INT32),
                      F(3, "starEnergy", K.INT32)),
    "ExploreSpeed": (F(1, "code", K.ENUM), F(2, "exploreEndTime", K.INT32),
                     F(3, "exploreId", K.INT32)),
    "FinishExplore": (F(1, "code", K.ENUM), F(2, "exploreId", K.INT32),
                      F(3, "rewardData", K.MESSAGE), F(4, "ruinId", K.INT32),
                      F(5, "exp", K.INT32)),
    "StartTrain": (F(1, "code", K.ENUM), F(2, "trainId", K.INT32),
                   F(3, "diffdifficulty", K.INT32), F(4, "trainTime", K.INT32),
                   F(5, "heroId", K.INT32), F(6, "trainEndTime", K.INT32),
                   F(7, "starEnergy", K.INT32), F(8, "buildId", K.INT32)),
    "CancelTrain": (F(1, "code", K.ENUM), F(2, "trainId", K.INT32),
                    F(3, "starEnergy", K.INT32)),
    "FinishTrain": (F(1, "code", K.ENUM), F(2, "trainId", K.INT32), F(3, "heroId", K.INT32),
                    F(4, "heroLevel", K.INT32), F(5, "heroExp", K.INT32),
                    F(6, "gainExp", K.INT32)),
    "BuildStartPrayGod": (F(1, "code", K.ENUM), F(2, "buildingId", K.INT32),
                          F(3, "heroStatus", K.ENUM), F(4, "prayTime", K.INT32),
                          F(5, "endTime", K.INT32)),
    "BuildCancelPrayGod": (F(1, "code", K.ENUM), F(2, "buildingId", K.INT32)),
    "BuildRewardPrayGod": (F(1, "code", K.ENUM), F(2, "buildingId", K.INT32),
                           F(4, "rewardData", K.MESSAGE)),  # Native Serialize: tag 0x22.
    "BuildQuickenPrayGod": (F(1, "code", K.ENUM), F(2, "buildingId", K.INT32),
                            F(3, "endTime", K.INT32)),
    "SingleCustomerInfo": (F(1, "code", K.ENUM), F(2, "posIndex", K.INT32),
                           F(3, "customere", K.MESSAGE), F(4, "transactionNum", K.INT32),
                           F(5, "transactionLastRecoverTime", K.INT32)),
    "MakeItem": (F(1, "code", K.ENUM), F(2, "posIndex", K.INT32),
                 F(3, "productionBar", K.MESSAGE)),
    "MakIngSpeed": (F(1, "code", K.ENUM), F(2, "posIndex", K.INT32)),
    "AlchemyMainData": (F(1, "code", K.ENUM), F(2, "recipeIdExp", K.MESSAGE, repeated=True),
                        F(3, "customeres", K.MESSAGE, repeated=True),
                        F(4, "productionBars", K.MESSAGE, repeated=True),
                        F(5, "elements", K.MESSAGE, repeated=True), F(6, "buffType", K.INT32),
                        F(7, "buffCount", K.INT32)),
    "AlchemyFinish": (F(1, "code", K.ENUM), F(2, "type", K.INT32), F(3, "posIndex", K.INT32),
                      F(4, "rewardData", K.MESSAGE), F(5, "alchemyType", K.INT32)),
    "AlchemyButtonClick": (F(1, "code", K.ENUM), F(2, "type", K.INT32),
                           F(3, "posIndex", K.INT32), F(4, "result", K.INT32),
                           F(5, "param", K.INT32)),
    "AlchemyCollect": (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE),
                       F(3, "recipeId", K.INT32), F(4, "exp", K.INT32),
                       F(5, "posIndex", K.INT32)),
    "AlchemyBuy": (F(1, "code", K.ENUM),),
    "AlchemyMakeCancel": (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE),
                          F(3, "posIndex", K.INT32)),
    "AlchemyOnekeyCollect": (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE),
                             F(3, "barData", K.MESSAGE, repeated=True)),
    "WashingRoomRandomAttri": (F(1, "code", K.ENUM), F(2, "equipID", K.INT32),
                               F(3, "equipParam", K.MESSAGE), F(4, "washingCountDay", K.INT32)),
    "WashingRoomOpt": (F(1, "code", K.ENUM), F(2, "equipID", K.INT32), F(3, "opt", K.INT32),
                       F(4, "equipParam", K.MESSAGE), F(5, "washingCountDay", K.INT32),
                       F(6, "rewardData", K.MESSAGE)),
    "SetAssistHero": (F(1, "code", K.ENUM), F(2, "heroID", K.INT32)),
    "QueryFirstReCharge": (F(1, "code", K.ENUM), F(2, "state", K.INT32)),
    "QueryAccumulateReCharge": (F(1, "code", K.ENUM),
                                F(2, "accumulateReChargeDataList", K.MESSAGE, repeated=True),
                                F(3, "totalMoney", K.INT32), F(4, "totalRechargeExp", K.INT32)),
    "HelpPowerSpeed": (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE),
                       F(3, "helpPowerSpeedParam", K.MESSAGE, repeated=True),
                       F(4, "helpPower", K.INT32), F(5, "helpPowerSpeed", K.MESSAGE)),
    "HelpPowerSpeedValid": (F(1, "code", K.ENUM), F(2, "type", K.INT32)),
}

COLLEGE_SCHEMAS = {
    "C2L_" + name: ProtoSchema("C2L_" + name, _C2L_FIELDS[name])
    for name, _, _ in COLLEGE_IDS
}
COLLEGE_SCHEMAS.update({
    "L2C_" + name: ProtoSchema("L2C_" + name, _L2C_FIELDS[name])
    for name, _, _ in COLLEGE_IDS
})
COLLEGE_SCHEMAS.update({
    schema.name: schema for schema in (EQUIP_PARAM, HELP_POWER_SPEED_PARAM, ACCUMULATE_RECHARGE_DATA)
})
COLLEGE_SCHEMAS['L2C_UpLevelBuildingId'] = ProtoSchema('L2C_UpLevelBuildingId', (
    F(1, 'buildingId', K.INT32),))
COLLEGE_SCHEMAS['L2C_TrainingUpdate'] = ProtoSchema('L2C_TrainingUpdate', (
    F(1, 'trainList', K.MESSAGE, repeated=True),))
COLLEGE_SCHEMAS['L2C_PrayEnd'] = ProtoSchema('L2C_PrayEnd', (F(1, 'buildingId', K.INT32),))

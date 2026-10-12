"""好友 (FriendService) 的 PBS HTTP 服务 + 人机玩家名册。

为什么要这个文件
----------------
客户端的好友页不走 TCP 消息, 而是登录进城后往 PBS HTTP 发短请求。离线参考实现
(x2offline/src/server/pbs_replies.inc) 把整批 FriendService.* / ClubService.* 一律回
静态空 JSON, 而且 GetFriendList 那份静态数据还少了 ``applys`` 键, 所以好友页永远空白。
本文件按玩家动态返回, 并用 ``data/ai_players.json`` 的名册充当好友。

人机名册
--------
名字 = 对应神格名, 头像 = 该神格 standard 头像 (生成器 ``work/make_ai_players.py``)。
名册里 39 条, 正好是客户端 head_icons / favor_catalog 的白名单英雄。

人机行为 (用户需求)
--------------------
* 默认同意好友请求: 玩家对某人机发 ApplyAddFriend -> 立刻成为好友。
* 首次拉列表时铺一小撮"欢迎好友" (WELCOME_FRIENDS 个), 好友页立刻有内容。
  **不能铺整份名册**: "搜索路人"的推荐名单 (lobby.recommend_player_cards) 与好友
  名册是同一份 ai_roster(), 全铺会让每一个推荐路人"已经是好友", 于是点「加好友」
  永远是 INSERT OR IGNORE 空操作 —— 申请发出去了、回包也是成功, 但好友数不涨、
  客户端也看不到任何变化 (用户实测反馈)。只铺 5 个, 其余 34 个留给玩家自己加。
* 每日自动赠送友情点: 每个好友每天给玩家一份 友情点(1237917), 累积上限 5000
  (客户端物品说明: "友情点最多可累积5000点, 达到累积上限后不再增加")。

为什么可以直接写 inventory
--------------------------
友情点 1237917 在客户端物品表里是 ItemType 16 (E_Currency) 且 ItemUseScence 是
E_Outside, 不在 EconomyService.CURRENCIES 的 snapshot 货币槽里, 所以它落在 ``inventory``
表 (economy._grant 的 else 分支)。登录报文 BaseInfo.FriendCoin (字段 30) 由
``login.PROFILE_CURRENCIES`` 从背包读数, 因此这里只需要写 inventory 一张表, 不需要碰
``players.snapshot`` —— HTTP worker 线程直接写它也不会和事件循环的 revision 冲突。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections.abc import Sequence
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from x2server.messages.lobby import LOBBY_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError

from .server_clock import ServerClock

LOG = logging.getLogger("x2.social")

# 友情点 (客户端物品说明: 最多累积 5000)。ItemType 16 / useScene Outside, 落背包。
FRIEND_COIN_ITEM = 1237917
FRIEND_COIN_CAP = 5000
# 每个好友每天赠送一份, 数量取客户端自己的 FriendLevel 表 (GiveFriendCoin /
# ReceiveFriendCoin 两档都是 20)。客户端弹的「向{0}赠送并获得{1}友情点」用的也是
# 这张表的数值, 服务端必须发同一个数, 否则飘字和实际到账对不上。
FRIEND_COIN_PER_FRIEND = 20
# 每日最多收取 15 名好友赠送的友情点 (language_runtime.json:2810384
# 「每日最多收取15名好友赠送的友情点」)。人机每日赠送按好友顺序只结前 15 个。
DAILY_RECEIVE_FRIENDS = 15
# 首次铺好友只铺这么多个"欢迎好友"。整份名册 (39) 不能铺, 因为推荐路人用的是同一
# 份名册, 全铺会让「加好友」永远无效果 —— 详见模块顶部 docstring。
WELCOME_FRIENDS = 5
# 铺好友规则的版本号 (social_seeded.ver)。1 = 只铺欢迎好友 + 收敛"整份名册"老存档。
SEED_VERSION = 1

# 客户端 ClubJoinType__Enum: 0=Unlimited 1=Confirm 2=RejectAll 3=Mixed。
# GetClub 回的 ClubData.Type 是"加入策略", 未入会时客户端按 Id==0 判定。
CLUB_JOIN_UNLIMITED = 0


@lru_cache(maxsize=1)
def ai_roster() -> tuple[dict[str, Any], ...]:
    """人机名册, 顺序稳定 (按 hero 升序, 生成器已排好)。"""
    payload = json.loads(
        files("x2server").joinpath("data/ai_players.json").read_text(encoding="utf-8"))
    return tuple(payload["players"])


def _roster_entry(uid: str) -> dict[str, Any] | None:
    for entry in ai_roster():
        if entry["uid"] == uid:
            return entry
    return None


def client_player_id(uid: str) -> str:
    """内部名册 uid -> 客户端使用的**数字玩家号** (ai1003 -> "1003")。

    名册 uid 是 "aiXXXX" 这种字符串, 但客户端的 FriendModule 把好友存成
    ``ListFriendID : List<Int64>`` 与 ``Dictionary<Int64, FriendPlayerInfo>``
    (名片的 ShowCardBase.playerID 同样是 int64), 拿到 "ai1003" 解析不出 int64,
    列表就是 0/200 —— 服务端返回了 39 条, 客户端仍显示「(0/200), 有朋友一起的话…」。

    「搜索路人」(lobby.recommend_player_cards) 早就是数字形态 (ai1003 -> 1003),
    玩家点「加好友」发回来的也是这个数字; 内部存储继续用 aiXXXX (social_friends 表
    与 ``_target_uid`` 的既有约定), 只在**下发报文**里换成数字, 两边就能对上。
    """
    return uid[2:] if uid.startswith("ai") and uid[2:].isdigit() else uid


def ensure_social_schema(db) -> None:
    """好友 / 好友申请 / 黑名单 / 赠送记录。HTTP 线程与事件循环共用同一份定义。"""
    db.execute("""CREATE TABLE IF NOT EXISTS social_friends (
        player_id INTEGER NOT NULL, uid TEXT NOT NULL, time INTEGER NOT NULL,
        PRIMARY KEY (player_id, uid))""")
    # 好友申请 (收到的)。人机默认同意, 所以这张表多数时候是空的, 但玩家可以
    # 主动给人机发申请 —— 那时我们直接建好友, 不在这里留痕。
    db.execute("""CREATE TABLE IF NOT EXISTS social_applys (
        player_id INTEGER NOT NULL, uid TEXT NOT NULL, time INTEGER NOT NULL,
        PRIMARY KEY (player_id, uid))""")
    db.execute("""CREATE TABLE IF NOT EXISTS social_blacks (
        player_id INTEGER NOT NULL, uid TEXT NOT NULL, time INTEGER NOT NULL,
        PRIMARY KEY (player_id, uid))""")
    # 每日友情点: 每个 (玩家,好友) 每天只记一行, 天然幂等。
    # collected=0 表示人机已经把点送出来了、但玩家还没点「收取」(待收取);
    # collected=1 表示玩家已经收下并已入账。这个区分是客户端按钮状态机的核心:
    # this+0x70(可收取列表) 由 FriendItem.Values 的 FriendCoin=1 填充, 而
    # FriendData.ReceivePlayer 只登记「已收取」的好友, 两者必须能分开。
    db.execute("""CREATE TABLE IF NOT EXISTS social_gifts (
        player_id INTEGER NOT NULL, uid TEXT NOT NULL, day INTEGER NOT NULL,
        collected INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (player_id, uid, day))""")
    columns = {row[1] for row in db.execute("PRAGMA table_info(social_gifts)")}
    if "collected" not in columns:
        db.execute("ALTER TABLE social_gifts ADD COLUMN collected INTEGER NOT NULL DEFAULT 0")
    # 玩家「赠送友情点」给好友的记录: 每个 (玩家,好友) 每天一次 (客户端也是这个口径)。
    # 兼作名片里 sendCoinPlayers 的数据源 —— 客户端按它把「赠送」按钮置成「已赠送」。
    db.execute("""CREATE TABLE IF NOT EXISTS social_send_coins (
        player_id INTEGER NOT NULL, uid TEXT NOT NULL, day INTEGER NOT NULL,
        PRIMARY KEY (player_id, uid, day))""")
    # 铺好友只做一次的标记。没有它就只能靠"好友数是否为 0"判断, 玩家一旦删光好友
    # 就会被重新铺一遍, 删好友等于无效。有了标记, 删光就是删光。
    # ver: 铺好友规则的版本号。老存档是"整份名册全铺"(无 ver 列, 视为 0), 收紧成
    # "只铺欢迎好友"后必须能识别并收敛它们, 所以版本要落库, 不能只看"有没有标记"。
    db.execute("""CREATE TABLE IF NOT EXISTS social_seeded (
        player_id INTEGER PRIMARY KEY, time INTEGER NOT NULL,
        ver INTEGER NOT NULL DEFAULT 0)""")
    columns = {row[1] for row in db.execute("PRAGMA table_info(social_seeded)")}
    if "ver" not in columns:
        db.execute("ALTER TABLE social_seeded ADD COLUMN ver INTEGER NOT NULL DEFAULT 0")


def day_of(now: float) -> int:
    """自然日编号 (与项目其它每日玩法一致: 东八区, 系统时间 // 86400)。"""
    return (int(now) + 8 * 3600) // 86400


def _client_number(uid: str) -> int | None:
    text = client_player_id(uid)
    return int(text) if text.isdigit() else None


def friend_data_values(db, player_id: int, now: float) -> bytes | None:
    """PlayerDataProto.FriendData (字段 10) 的编码值, 表未建时返回 None。

    客户端 FriendModule_SendFriendCoin (0x015225B4) 拿 ``SendPlayer`` 跳过今天已赠送的
    好友、拿 ``SendCount`` 算「还能送几个」; FriendModule_GetFriendCoinStatus
    (0x01530318) 拿 ``ReceivePlayer`` 区分「可收取 / 已收取」。服务端此前从不推这个成员
    (PlayerData__ctor 只是把它建成空对象), 于是按钮状态永远回不到「已赠送/已收取」。

    取数直接读同一份 sqlite (social_gifts / social_send_coins), 与 SocialReader 同一张
    表, 所以 HTTP 线程刚写下的记录, 事件循环这次推送就能看到。表还没建 (单测里没起
    SocialReader) 时捕获 OperationalError 返回 None, 保持旧的「成员缺席」形状。
    """
    from x2server.messages.core import CONTAINER_INT_INT64, FRIEND_DATA

    today = day_of(now)
    try:
        gifts = db.execute(
            "SELECT uid, collected FROM social_gifts WHERE player_id=? AND day=?",
            (player_id, today)).fetchall()
        sends = db.execute(
            "SELECT uid FROM social_send_coins WHERE player_id=? AND day=?",
            (player_id, today)).fetchall()
    except sqlite3.OperationalError:
        return None
    sent = [int(n) for n in (_client_number(str(row[0])) for row in sends) if n is not None]
    received = [int(n) for n in (_client_number(str(row[0])) for row in gifts if int(row[1]))
                if n is not None]
    def containers(numbers: list[int]) -> list[bytes]:
        return [CONTAINER_INT_INT64.encode({"idx": index, "val": number})
                for index, number in enumerate(numbers)]
    return FRIEND_DATA.encode({"SendPlayer": containers(sent),
                               "ReceivePlayer": containers(received),
                               "SendCount": len(sent), "ReceiveCount": len(received)})


class SocialReader:
    """好友 PBS 路由的读取/写入端。

    ``ThreadingHTTPServer`` 从 worker 线程服务 HTTP, 所以这里自带一条连接:
    ``PlayerStore.db`` 属于事件循环, 绝不能共给 worker 线程。
    """

    def __init__(self, path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        ensure_social_schema(self.db)
        self.db.commit()

    def close(self) -> None:
        with self._lock:
            self.db.close()

    # ---- 内部工具 -------------------------------------------------------

    def _friends(self, player_id: int) -> list[str]:
        with self._lock:
            rows = self.db.execute(
                "SELECT uid FROM social_friends WHERE player_id=? ORDER BY time, uid",
                (player_id,)).fetchall()
        return [row["uid"] for row in rows]

    def _owner_snapshot(self, player_id: int) -> dict[str, Any]:
        row = self.db.execute("SELECT snapshot FROM players WHERE id=?", (player_id,)).fetchone()
        if row is None:
            return {}
        try:
            return json.loads(row["snapshot"])
        except (TypeError, ValueError):
            return {}

    def seed_friends(self, player_id: int, now: float) -> None:
        """首次铺一小撮欢迎好友, 之后永不重复 (幂等: social_seeded.ver 版本号)。

        为什么只铺 WELCOME_FRIENDS 个而不是整份名册: 客户端「搜索路人」的推荐名单
        (lobby.recommend_player_cards) 用的就是同一份 ai_roster(), 全铺会让推荐路人
        全部"已经是好友", 玩家点「加好友」时 add_friend 只是 INSERT OR IGNORE 空操作
        —— 请求成功、回包成功, 但好友数不涨, 客户端也看不到任何变化。

        旧存档收敛 (ver < SEED_VERSION): 老版本一次性铺过整份名册, 这里把它压回
        WELCOME_FRIENDS 个, 让那些推荐路人重新变成"可加"。
        ★ 判据不能用"好友数 == 名册长度": 名册后来加过人 (39 -> 40 的「蓝色鸟」),
        老存档停在 39 就永远不匹配, 收敛失效、标记还被写上, 从此再也不会铺 —— 之前
        就是这么坏的。改成"ver 版本 + 有好友"来判断, 与名册长度解耦。
        玩家删光好友后不再被重新塞回 —— 删就是删, 由版本号保证。
        """
        roster = ai_roster()
        with self._lock:
            row = self.db.execute(
                "SELECT ver FROM social_seeded WHERE player_id=?", (player_id,)).fetchone()
            version = int(row[0]) if row is not None else 0
            if version >= SEED_VERSION:
                return
            with self.db:
                friends = self._friends(player_id)
                # 老版本整批铺过 (有好友但没有版本号) -> 清掉, 只留欢迎好友。
                if version < SEED_VERSION and friends:
                    self.db.execute("DELETE FROM social_friends WHERE player_id=?", (player_id,))
                    friends = []
                if not friends:
                    for index, entry in enumerate(roster[:WELCOME_FRIENDS]):
                        self.db.execute(
                            "INSERT OR IGNORE INTO social_friends VALUES (?,?,?)",
                            (player_id, entry["uid"], int(now) + index))
                self.db.execute(
                    """INSERT INTO social_seeded VALUES (?,?,?)
                       ON CONFLICT(player_id) DO UPDATE SET time=excluded.time, ver=excluded.ver""",
                    (player_id, int(now), SEED_VERSION))

    def add_friend(self, player_id: int, uid: str, now: float) -> None:
        if _roster_entry(uid) is None:
            return
        with self._lock, self.db:
            self.db.execute("INSERT OR IGNORE INTO social_friends VALUES (?,?,?)",
                            (player_id, uid, int(now)))
            self.db.execute("DELETE FROM social_applys WHERE player_id=? AND uid=?",
                            (player_id, uid))
            self.db.execute("DELETE FROM social_blacks WHERE player_id=? AND uid=?",
                            (player_id, uid))

    def remove_friend(self, player_id: int, uid: str) -> None:
        with self._lock, self.db:
            self.db.execute("DELETE FROM social_friends WHERE player_id=? AND uid=?",
                            (player_id, uid))

    def is_friend(self, player_id: int, uid: str) -> bool:
        with self._lock:
            row = self.db.execute("SELECT 1 FROM social_friends WHERE player_id=? AND uid=?",
                                  (player_id, uid)).fetchone()
        return row is not None

    # ---- 每日友情点 -----------------------------------------------------

    def daily_login(self, player_id: int, now: float) -> int:
        """登录时登记当天的好友赠送: 先铺好友(首次), 再把人机的「赠礼」摆出来。

        登录路径在 L2C_Login 的 BaseInfo push 之前调用它。注意这里**不入账** ——
        人机送出的友情点要玩家自己在好友页点「收取」才到账(见 receive_friend_coin),
        这正是客户端按钮状态机(FriendCoinStatus.CanReceive)要求的口径。
        """
        self.seed_friends(player_id, now)
        return self.daily_gift(player_id, now)

    def daily_gift(self, player_id: int, now: float) -> int:
        """登记人机当天的赠礼(待收取), 返回本次新登记的好友数。

        * 每个 (好友, 当天) 只登记一次 (social_gifts 主键), 反复拉列表不会重复摆。
        * 每天最多登记 DAILY_RECEIVE_FRIENDS 个好友 (客户端口径: 每日最多收取 15 名
          好友赠送的友情点), 多出来的好友当天不再赠送。
        * **只登记, 不入账**。点数在 receive_friend_coin 里按 FRIEND_COIN_PER_FRIEND
          结算, 并受 FRIEND_COIN_CAP 封顶。
        """
        friends = self._friends(player_id)
        if not friends:
            return 0
        today = day_of(now)
        with self._lock:
            gifted = {row["uid"] for row in self.db.execute(
                "SELECT uid FROM social_gifts WHERE player_id=? AND day=?",
                (player_id, today)).fetchall()}
            pending = [uid for uid in friends if uid not in gifted][:DAILY_RECEIVE_FRIENDS]
            if not pending:
                return 0
            with self.db:
                for uid in pending:
                    self.db.execute("INSERT OR IGNORE INTO social_gifts VALUES (?,?,?,0)",
                                    (player_id, uid, today))
        LOG.info("好友每日赠礼(待收取) player=%s friends=%d", player_id, len(pending))
        return len(pending)

    def receive_friend_coin(self, player_id: int, numbers: Sequence[object],
                            now: float) -> int:
        """玩家收取好友赠送的友情点 (C2L_ReceiveFriendCoin 436), 返回实际入账点数。

        * ``numbers`` 是要收取的好友数字号; 为空表示「全部收取」(客户端有时把
          this+0x70 整个送上来)。
        * 只有 social_gifts 里 collected=0 的行才是可收取的; 每个好友每天只结算一次。
        * 每天最多收 DAILY_RECEIVE_FRIENDS 名好友 (与 IsReceiveFriendCoinMax 的上限
          同一口径), 收满后剩下的留在原地等明天。
        * 点数受 FRIEND_COIN_CAP (5000) 封顶, 返回值是**真正加进背包**的点数。
        """
        friends = set(self._friends(player_id))
        wanted: list[str] = []
        for number in numbers:
            uid = self._target_uid({"playerid": number})
            if uid and uid in friends and uid not in wanted:
                wanted.append(uid)
        today = day_of(now)
        with self._lock:
            pending = {row["uid"] for row in self.db.execute(
                "SELECT uid FROM social_gifts WHERE player_id=? AND day=? AND collected=0",
                (player_id, today)).fetchall()}
            targets = [uid for uid in (wanted or self._friends(player_id)) if uid in pending]
            if not targets:
                return 0
            received = self.db.execute(
                "SELECT COUNT(*) FROM social_gifts WHERE player_id=? AND day=? AND collected=1",
                (player_id, today)).fetchone()[0]
            targets = targets[:max(0, DAILY_RECEIVE_FRIENDS - int(received))]
            if not targets:
                return 0
            gained = self._credit_friend_coin(player_id, FRIEND_COIN_PER_FRIEND * len(targets))
            with self.db:
                for uid in targets:
                    self.db.execute(
                        "UPDATE social_gifts SET collected=1 WHERE player_id=? AND uid=? AND day=?",
                        (player_id, uid, today))
        LOG.info("收取友情点 player=%s friends=%d points=%d", player_id, len(targets), gained)
        return gained

    def pending_numbers(self, player_id: int, now: float) -> list[int]:
        """今天「已由人机送出、玩家尚未收取」的好友数字号 (FriendCoin=1 的那批)。"""
        today = day_of(now)
        with self._lock:
            rows = self.db.execute(
                "SELECT uid FROM social_gifts WHERE player_id=? AND day=? AND collected=0",
                (player_id, today)).fetchall()
        return [number for number in (self._number(str(row["uid"])) for row in rows)
                if number is not None]

    @staticmethod
    def _number(uid: str) -> int | None:
        text = client_player_id(uid)
        return int(text) if text.isdigit() else None

    def _credit_friend_coin(self, player_id: int, amount: int) -> int:
        """给玩家账户加友情点, 封顶 FRIEND_COIN_CAP; 返回**实际**加进去的点数。

        调用方必须已持有 ``self._lock``, 并在同一个事务里写 social_gifts /
        social_send_coins —— 先算额度再加, 才能与"每天只发一次"的记账原子。
        """
        if amount <= 0:
            return 0
        balance = self.db.execute(
            "SELECT quantity FROM inventory WHERE player_id=? AND item_id=?",
            (player_id, FRIEND_COIN_ITEM)).fetchone()
        current = int(balance[0]) if balance is not None else 0
        granted = min(amount, max(0, FRIEND_COIN_CAP - current))
        if granted <= 0:
            return 0
        self.db.execute(
            """INSERT INTO inventory VALUES (?,?,?)
               ON CONFLICT(player_id,item_id)
               DO UPDATE SET quantity=quantity+excluded.quantity""",
            (player_id, FRIEND_COIN_ITEM, granted))
        return granted

    # ---- 玩家赠送友情点 (C2L_SendFriendCoin 434) -------------------------------

    def friend_numbers(self, player_id: int) -> set[int]:
        """该玩家好友的**数字玩家号**集合 (ai1003 -> 1003), 供推荐页排重。"""
        numbers: set[int] = set()
        for uid in self._friends(player_id):
            text = client_player_id(uid)
            if text.isdigit():
                numbers.add(int(text))
        return numbers

    def send_friend_coin(self, player_id: int, numbers: Sequence[object],
                         now: float) -> tuple[int, int]:
        """玩家向好友赠送友情点: 每个好友每天只能送一次, 送出的同时也获得友情点。

        客户端文案 (language_runtime.json:13102073) 是「向{0}赠送并获得{1}友情点」——
        赠送方自己也得到 FriendLevel.ReceiveFriendCoin (=FRIEND_COIN_PER_FRIEND) 点,
        所以这里给**赠送者**加友情点, 而不是给只会是人机的好友。返回
        ``(本次新赠送的好友数, 真正入账的点数)``: 前者给每日任务 630023 (赠送次数),
        后者给成就 660010「累计获得友情点」——点数受 5000 上限封顶, 必须用实际入账值。
        """
        friends = set(self._friends(player_id))
        if not friends:
            return 0, 0
        today = day_of(now)
        fresh: list[str] = []
        with self._lock:
            sent = {row["uid"] for row in self.db.execute(
                "SELECT uid FROM social_send_coins WHERE player_id=? AND day=?",
                (player_id, today)).fetchall()}
            for number in numbers:
                uid = self._target_uid({"playerid": number})
                if not uid or uid not in friends or uid in sent:
                    continue
                sent.add(uid)
                fresh.append(uid)
            if not fresh:
                return 0, 0
            gained = self._credit_friend_coin(player_id, FRIEND_COIN_PER_FRIEND * len(fresh))
            with self.db:
                for uid in fresh:
                    self.db.execute("INSERT OR IGNORE INTO social_send_coins VALUES (?,?,?)",
                                    (player_id, uid, today))
        LOG.info("赠送友情点 player=%s friends=%d points=%d", player_id, len(fresh), gained)
        return len(fresh), gained

    def sent_numbers(self, player_id: int, now: float) -> list[int]:
        """今天已赠送过友情点的好友数字号列表 (名片 sendCoinPlayers)。"""
        today = day_of(now)
        with self._lock:
            rows = self.db.execute(
                "SELECT uid FROM social_send_coins WHERE player_id=? AND day=?",
                (player_id, today)).fetchall()
        numbers: list[int] = []
        for row in rows:
            text = client_player_id(str(row["uid"]))
            if text.isdigit():
                numbers.append(int(text))
        return numbers

    # ---- 报文构造 -------------------------------------------------------

    @staticmethod
    def _attrib(uid: str, name: str, head: int, level: int, online: bool = True) -> dict[str, Any]:
        """BaseAttrib (pbs) —— 好友/社团列表里每个人都是这个结构。"""
        return {"Uid": uid, "CreateTime": 0, "Name": name, "Head": str(head),
                "Level": level, "Zone": "", "Server": "local", "Channel": "local",
                "SubChannel": "", "Os": "", "Online": online, "Ext": {}}

    def _friend_items(self, player_id: int, now: float) -> list[dict[str, Any]]:
        """好友列表的每一行。``Values`` 里带 FriendCoin=1 的那批就是「有礼可收」。

        客户端 FriendModule_RefreshFriendInfo (0x01526B6C) 遍历 Values, 遇到
        ``Name == "FriendCoin"`` 且 ``Value.VInt64 == 1`` 就把该好友塞进 this+0x70
        (可收取列表); FriendModule_GetFriendCoinStatus (0x01530318) 正是靠这个列表
        才可能返回 CanReceive(1)。本服务端此前恒发 ``"Values": []``, 所以好友页从来
        没有「收取」入口 —— 用户反馈的「收不到人机送的友情点」就是这里。
        Value 的 JSON 形状与 player/club.py 里 ClubData 的一致:
        ``{"Type": 1, "VString": "", "VInt64": 1}`` (ValueType.Integer)。
        """
        today = day_of(now)
        with self._lock:
            pending = {row["uid"] for row in self.db.execute(
                "SELECT uid FROM social_gifts WHERE player_id=? AND day=? AND collected=0",
                (player_id, today)).fetchall()}
        items = []
        for uid in self._friends(player_id):
            entry = _roster_entry(uid)
            if entry is None:
                continue
            values = ([{"Name": "FriendCoin", "Value": {"Type": 1, "VString": "", "VInt64": 1}}]
                      if uid in pending else [])
            items.append({
                # Friendid / Attrib.Uid 都必须是数字玩家号, 见 client_player_id。
                "Friendid": client_player_id(uid),
                # Nickname 是玩家给好友设的备注; 客户端为空时回退 Attrib.Name。
                "Nickname": "",
                "Time": 0,
                "Online": True,
                "Values": values,
                "SharingValues": [],
                "Attrib": self._attrib(client_player_id(uid), entry["name"], entry["head"],
                                       entry["level"]),
            })
        return items

    def _apply_items(self, player_id: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.execute(
                "SELECT uid,time FROM social_applys WHERE player_id=? ORDER BY time",
                (player_id,)).fetchall()
        items = []
        for row in rows:
            entry = _roster_entry(row["uid"])
            if entry is None:
                continue
            items.append({"Friendid": client_player_id(row["uid"]), "Time": int(row["time"]),
                          "Online": True,
                          "Attrib": self._attrib(client_player_id(row["uid"]), entry["name"],
                                                 entry["head"], entry["level"])})
        return items

    def _black_items(self, player_id: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.execute(
                "SELECT uid,time FROM social_blacks WHERE player_id=? ORDER BY time",
                (player_id,)).fetchall()
        items = []
        for row in rows:
            entry = _roster_entry(row["uid"])
            if entry is None:
                continue
            items.append({"Friendid": client_player_id(row["uid"]), "Time": int(row["time"]),
                          "Attrib": self._attrib(client_player_id(row["uid"]), entry["name"],
                                                 entry["head"], entry["level"], online=False)})
        return items

    def friend_list(self, player_id: int, now: float) -> dict[str, Any]:
        """GetFriendList 的 Data。GetFriendListReply.Friends 本身是 FriendList 包装对象,
        直接给数组会 JsonSerializationException —— 实测踩坑 (protocol/README.md §8)。"""
        self.seed_friends(player_id, now)
        self.daily_gift(player_id, now)
        # 申请列表为空时必须给 **null** (None -> JSON null), 不能给非 null 空数组:
        # 客户端 FriendModule_GetFriendCallback 在 RefreshApplyInfo 返回真时点亮申请页签
        # 红点 (BadgeViewMgr.SetValue(TabBadgeDic[2], 1))。RefreshApplyInfo (RVA 0x01527388)
        # 只在入参为 null 时返回 0, 非 null 时返回「旧 ListApplyID 是否为空」, 而本地旧列表
        # 恒为空 -> 返回真 -> 每次拉好友列表都把红点重新点亮, 这就是「申请为空却常亮红点」。
        applys = self._apply_items(player_id)
        return {"Friends": {"Friends": self._friend_items(player_id, now),
                            "Applys": applys or None,
                            "Blacks": self._black_items(player_id),
                            "SendApplys": []}}

    # ---- 名片 (/apply/queryPlayer) --------------------------------------

    def public_cards(self, player_ids: Sequence[object], now: float | None = None) -> list[dict[str, Any]]:
        """``/apply/queryPlayer`` 的 datas: 每个被查 id 一张 FriendShowCard。

        客户端 ``FriendModule.QueryPlayerHttp`` 是好友页/申请页/黑名单/聊天页共用的
        批量拉名片: 表单只有一个 ``players`` (JSON 数字数组), 期待
        ``{"code":0,"datas":[...]}`` 并且**每个被查 id 都要有卡**。``datas`` 为空/缺卡
        时它会弹「请稍后再试,小破船可能漏水了」—— 这条 ``/apply/*`` 路由此前完全没实现
        (HTTP 404), 所以每次进好友页都弹一次提示。

        数据取自同一份 ``ai_roster()``, 名字/头像/等级与好友列表 ``_friend_items`` 一致,
        名片和列表不会各说各话。查不到的 id 也回一张骨架卡 (只有 roleID + 空子结构),
        绝不留空 —— 缺一张就又是一次弹窗。子结构字段名照抄客户端类型
        (work/cpp/appdata/il2cpp-types.h 的 FriendShowCard/ShowCardBase/ShowCardExtra/
        ShowAssistHero), 用 LitJson 默认的成员名反序列化。

        ``sendCoinPlayers`` = 今天给这张名片的人送过友情点的玩家号。客户端按
        ``sendCoinPlayers.Contains(自己)`` 把「赠送」按钮置成「已赠送」, 缺了它重登后
        每个好友又变成可赠送。这条请求不带身份, 所以取"今天送过的人"; 本地只有一个
        真实玩家, 结果等价。
        """
        today = day_of(now if now is not None else time.time())
        cards: list[dict[str, Any]] = []
        for value in player_ids:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            entry = _roster_entry(f"ai{number}") if number > 0 else None
            name = str(entry["name"]) if entry is not None else ""
            level = int(entry["level"]) if entry is not None else 1
            head = int(entry.get("head", 0)) if entry is not None else 0
            # 支援神格: 每个好友就是「对应角色的人机」, 支援位给该角色的满级满星神格。
            # ShowAssistHero = {id, level, star, outerSkin}; level 120 / star 46 是
            # battle 入场校验的区间上界 (player/battle.py), 也是客户端 SupportHero
            # 能渲染的最满档。旧实现恒发全 0 -> 好友详情看不到支援神格, 主线也选不了。
            hero_id = int(entry["hero"]) if entry is not None else 0
            assist = {"id": hero_id, "level": 120 if hero_id else 0,
                      "star": 46 if hero_id else 0, "outerSkin": 0}
            with self._lock:
                senders = [int(row[0]) for row in self.db.execute(
                    "SELECT player_id FROM social_send_coins WHERE uid=? AND day=?",
                    (f"ai{number}", today)).fetchall()]
            cards.append({
                "roleID": number,
                "roleName": name,
                "roleLevel": level,
                "showCardExtra": {"autograph": "", "birthday": 0, "heroNum": 0,
                                  "achvPoint": 0, "hardestSectionId": 0, "achvPointMax": 0},
                "showCardBase": {
                    "iconInfo": {"iconType": 0, "iconID": head,
                                 "ornamentID": 0, "framePicId": 0},
                    "nickName": name, "roleLevel": level, "playerID": number,
                    "medalShow": {"pos": []}, "show": 0, "lastLogoutTime": 0,
                    "sendCoinPlayers": senders, "outerSkin": 0},
                "assistHero": assist,
                "playerInfoBrowse": 0,
            })
        return cards

    # ---- 路由分发 -------------------------------------------------------

    def handle(self, path: str, args: dict[str, Any], player_id: int,
               now: float) -> dict[str, Any]:
        """按路由返回 Data (外层信封由 local_identity 统一加)。"""
        # 客户端把目标玩家号放在 "playerid" 或 "friendid" / "userid" 里, 名字随
        # 方法不同 (pbs DTO 成员名), 三种都认, 取第一个能解析成人的。
        target = self._target_uid(args)

        if path in ("/FriendService.GetFriendList", "/FriendService.GetFriendListV2"):
            return self.friend_list(player_id, now)
        if path == "/FriendService.GetApplyList":
            return {"send_applys": [], "applys": self._apply_items(player_id)}
        if path == "/FriendService.GetBlackList":
            return {"blacks": self._black_items(player_id)}
        # 加好友 / 同意申请: 人机默认同意, 直接建好友关系。
        if path in ("/FriendService.ApplyAddFriend", "/FriendService.AddFriend",
                    "/FriendService.AnswerAddFriend"):
            if target:
                self.add_friend(player_id, target, now)
            return {}
        if path == "/FriendService.DeleteFriend":
            if target:
                self.remove_friend(player_id, target)
            return {}
        if path == "/FriendService.AddBlacklist":
            if target:
                self.remove_friend(player_id, target)
                with self._lock, self.db:
                    self.db.execute("INSERT OR IGNORE INTO social_blacks VALUES (?,?,?)",
                                    (player_id, target, int(now)))
            return {}
        if path == "/FriendService.RemoveBlacklist":
            if target:
                with self._lock, self.db:
                    self.db.execute("DELETE FROM social_blacks WHERE player_id=? AND uid=?",
                                    (player_id, target))
            return {}
        if path in ("/FriendService.FollowFriend", "/FriendService.UnfollowFriend",
                    "/FriendService.RenameFriend", "/FriendService.UpdateLimitParam",
                    "/FriendService.AddFriendValue", "/FriendService.UpdateStorage",
                    "/FriendService.UpdateStorageV2", "/FriendService.ForwardMsg",
                    "/FriendService.Truncate"):
            return {}
        return {}

    @staticmethod
    def _target_uid(args: dict[str, Any]) -> str:
        for key in ("friendid", "playerid", "userid", "id"):
            value = args.get(key)
            if value is None:
                continue
            text = str(value)
            if _roster_entry(text) is not None:
                return text
            # 客户端也可能把 uid 当数字发。名册 uid 是 aiXXXX, 用 "ai"+数字 再试一次。
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            candidate = f"ai{number}"
            if _roster_entry(candidate) is not None:
                return candidate
        return ""


class SocialFriendService:
    """好友的 TCP 消息 (C2L_SendFriendReq 453) 的应答端。

    客户端的「加好友」走 TCP: FriendModule_AddFriend -> FriendModule_SendFriendReq
    发 C2L_SendFriendReq (只带 playerid 列表), 等 L2C_SendFriendReq。此前这条只有
    消息号没有 handler, 客户端 request_id 一直 pending -> 超时重连。

    这里复用 PBS 侧同一个 SocialReader (人机默认同意加好友的语义一致), 不另开数据库
    连接 —— reader 自带 RLock, 从事件循环调用与 HTTP worker 线程调用等价。连接在
    run_server.py 里构造后传入。
    """

    def __init__(self, reader: "SocialReader | None", clock=None, economy=None,
                 store=None) -> None:
        self.reader = reader
        self.clock = clock or ServerClock()
        # 赠送友情点要往背包写 1237917 并让客户端立刻刷新数量, 所以借用 economy 的
        # inventory_values 组 L2C_ItemUpdate。为 None 时仍然记账发点, 只是不推送。
        self.economy = economy
        # 好友页的赠送/收取按钮状态存在 PlayerData.FriendData 里, 客户端收 435/437
        # 回包后不会自己算它; 因此每次记账后要补推一份新的 PlayerDataProto。构造器由
        # run_server.py 注入 (LoginService.snapshot_push), store 用来读快照与背包。
        self.store = store
        self.snapshot_push = None

    def handlers(self) -> dict:
        return {"C2L_SendFriendReq": self.send_friend_req,
                "C2L_SendFriendCoin": self.send_friend_coin,
                "C2L_ReceiveFriendCoin": self.receive_friend_coin}

    def _item_push(self, player_id: int):
        if self.economy is None:
            return ()
        return (OutboundMessage("L2C_ItemUpdate",
                                {"code": 10, **self.economy.inventory_values(player_id)}),)

    def _snapshot_pushes(self, player_id: int):
        """赠送/收取友情点后补推的整份 PlayerDataProto。

        客户端 FriendModule 的「今天还能送几个 / 这个好友已赠送·已收取」全靠
        PlayerData.FriendData 判定。435/437 的 handler
        (FriendModule_OnReceiveSendFriendCoinMsg 0x0152D4A0) 收到回包后**立刻**调
        FriendModule_UpdateFriendCoinStatus → GetFriendCoinStatus (0x01530318) 读
        FriendData.SendPlayer/ReceivePlayer 来定按钮状态, 所以这份快照必须在响应帧
        **之前**到 (调用方放进 OutboundMessage.before_response), 否则按钮读到旧值、
        停在初始态 —— 用户看到的就是「一键赠送点了没反应」。构造器与登录 push 共用
        (run_server.py 注入), 未接线时不推。
        """
        if self.snapshot_push is None or self.store is None:
            return ()
        from .login import LoginService
        fresh = self.store.get(player_id)
        return (self.snapshot_push(
            fresh,
            self.store.inventory_quantities(player_id, LoginService.profile_currency_items()),
            store=self.store),)

    async def send_friend_req(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("friend request before login")
        request = LOBBY_SCHEMAS["C2L_SendFriendReq"].decode(packet.body)
        targets = [int(value) for value in (request.get("playerid") or [])]
        added: list[int] = []
        if self.reader is not None:
            now = self.clock.now()
            for target in targets:
                # 名册 uid 是 aiXXXX, 客户端发来的是名片里的数字 playerID (ai1003 -> 1003),
                # 这里用 SocialReader 同一套解析 (数字 -> "ai"+数字)。
                uid = SocialReader._target_uid({"playerid": target})
                if not uid:
                    continue
                self.reader.add_friend(context.session.player_id, uid, now)
                added.append(target)
        LOG.info("好友申请(TCP 453) player=%s targets=%s added=%s",
                 context.session.player_id, targets, added)
        # 回包把请求里的 playerid 原样带回 (客户端用它和 mListAddFriendID 对账)。
        return OutboundMessage("L2C_SendFriendReq", {"code": 10, "playerid": targets})

    async def send_friend_coin(self, context, packet):
        """434 C2L_SendFriendCoin: 向好友赠送友情点。

        客户端 ``FriendModule_SendFriendCoin(playerID)`` 一次只送一个人, 请求里
        ``playerid`` / ``friendPoint`` 是两个一一对应的 list。服务端按好友关系校验,
        每个好友每天只记一次, 并给赠送者加 FRIEND_COIN_PER_FRIEND 点友情点 (客户端
        飘字「向{0}赠送并获得{1}友情点」), 再推一份 L2C_ItemUpdate 让数量立刻刷新。
        """
        if context.session.player_id is None:
            raise ProtocolError("friend coin before login")
        request = LOBBY_SCHEMAS["C2L_SendFriendCoin"].decode(packet.body)
        player_id = context.session.player_id
        targets = [int(value) for value in (request.get("playerid") or [])]
        granted = 0
        points = 0
        if self.reader is not None and targets:
            granted, points = self.reader.send_friend_coin(player_id, targets, self.clock.now())
        # 每日 630023「赠送好友 1 次友情点」(TaskCondition.CompleteType 71
        # E_GiveFriendCoin)。好友玩法接通后这里补上事件源: 成功赠送(reader 已按
        # 好友+当天去重)才记账, 同一批 targets 重发时 granted=0, 不会重复计。
        if granted and self.economy is not None:
            self.economy.record_event(
                player_id, f"sendcoin:{player_id}:{','.join(str(t) for t in sorted(targets))}",
                self.economy.TASK_EVENT_GIVE_FRIEND_COIN, 0, granted)
        # 成就 660010「累计获得友情点」按**实际入账点数**累计 (赠送方自己也获得一份,
        # 客户端文案「向{0}赠送并获得{1}友情点」)。必须用自定事件号, 不能复用 71:
        # 71 是「赠送次数」, 收取友情点再记 71 会把 630023「赠送 1 次」顶成已完成。
        if points and self.economy is not None:
            self.economy.achievements.record(
                player_id,
                f"friendcoin-gain:send:{player_id}:{day_of(self.clock.now())}:"
                f"{','.join(str(t) for t in sorted(targets))}",
                self.economy.ACHV_EVENT_FRIEND_COIN, points)
        LOG.info("赠送友情点(434) player=%s targets=%s granted=%s",
                 player_id, targets, granted)
        # 快照必须放在 before_response (响应帧之前发): 客户端处理 435 时会立刻用
        # FriendData.SendPlayer/ReceivePlayer 重算按钮状态 (FriendModule_
        # OnReceiveSendFriendCoinMsg -> UpdateFriendCoinStatus -> GetFriendCoinStatus),
        # 而 FriendModule_OnReceiveFriendDataDirty 只在每日上限用尽时才刷新 —— 若快照
        # 晚于 435 到达, 按钮读到的仍是赠送前的旧值, 表现为「一键赠送点了没反应」。
        # 不再带 granted 条件: granted=0 (重复赠送/已达每日上限) 时按钮同样要落到正确状态。
        return OutboundMessage("L2C_SendFriendCoin", {"code": 10, "playerid": targets},
                               before_response=self._snapshot_pushes(player_id),
                               pushes=self._item_push(player_id))

    async def receive_friend_coin(self, context, packet):
        """436 C2L_ReceiveFriendCoin: 收取好友赠送的友情点。

        人机的每日赠送在登录/拉好友列表时只**登记**成「待收取」(daily_gift), 玩家点
        「收取」时由 reader.receive_friend_coin 真正入账并把该好友置为「已收取」——
        与客户端 FriendCoinStatus.CanReceive -> Finish 的状态机一致。处理完补推一份
        新的 PlayerDataProto(_snapshot_pushes) + L2C_ItemUpdate, 让按钮翻面、余额刷新。
        """
        if context.session.player_id is None:
            raise ProtocolError("receive friend coin before login")
        request = LOBBY_SCHEMAS["C2L_ReceiveFriendCoin"].decode(packet.body)
        player_id = context.session.player_id
        targets = [int(value) for value in (request.get("playerid") or [])]
        gained = 0
        if self.reader is not None:
            gained = self.reader.receive_friend_coin(player_id, targets, self.clock.now())
        # 成就 660010「累计获得友情点」: 收取到的点数是**实际入账**值 (已封顶 5000),
        # reader 已按 (好友, 当天) 去重并把该好友置为「已收取」, 同一批 targets 重发时
        # gained=0, 不会重复累加。键含本地日, 隔天再收才算新的一笔。
        if gained and self.economy is not None:
            self.economy.achievements.record(
                player_id,
                f"friendcoin-gain:recv:{player_id}:{day_of(self.clock.now())}:"
                f"{','.join(str(t) for t in sorted(targets))}",
                self.economy.ACHV_EVENT_FRIEND_COIN, gained)
        LOG.info("收取友情点(436) player=%s targets=%s gained=%s",
                 player_id, targets, gained)
        # 同 send_friend_coin: 快照改到响应帧之前发, 客户端处理 437 时 FriendData
        # 已是最新, 按钮才能从 CanReceive 翻成 Finish; 且不再带 gained 条件。
        return OutboundMessage("L2C_ReceiveFriendCoin", {"code": 10, "playerid": targets},
                               before_response=self._snapshot_pushes(player_id),
                               pushes=self._item_push(player_id))
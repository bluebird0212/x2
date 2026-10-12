# 提案：好友系统 + 人机玩家（本地实现，仅供评估）

> **这不是 PR**，也不是请求合并。这里只是把我在**本地单机 fork** 里已经跑起来的一套
> 「好友系统 + 人机（AI）玩家」实现放出来，供维护者评估。**要不要合进主仓库、怎么合，完全由你决定。**
> 代码直接搬过去不能跑，见下面的「接入方式」。

## 这是什么

原版客户端有一套完整的好友/友情点/好友支援链路，但主仓库目前没有实现（`analysis/coverage/runtime_coverage.json`
里 `C2L_SendFriendCoin` 等仍是 `MISSING`）。这份实现把它补上了，并额外加了一批「人机玩家」，
让单机玩家也能有好友、能收友情点、好友支援位有神格可用。

具体行为：

- **好友**：加好友（`C2L_SendFriendReq`）、删好友、黑名单、好友列表下发。
- **友情点**：每日赠送 / 领取友情点（`C2L_SendFriendCoin` / `C2L_ReceiveFriendCoin`），
  带每日额度（每个好友每天可领一次，`DAILY_RECEIVE_FRIENDS` / `FRIEND_COIN_PER_FRIEND`）。
- **人机玩家**：`ai_players.json` 里 40 个人机（`ai1003`… 等），用对应神格的名字和头像；
  会出现在「添加好友」推荐里、默认同意好友请求、每天自动给玩家送友情点。
- **好友支援**：好友列表的 `assistHero` 会带一个可用的支援神格，不再恒为 0。
- 人机 uid 是字符串（`ai1003`），TCP 玩家号在 `client_player_id` 里映射成数字下发。

## 文件

| 文件 | 目标路径（主仓库内） | 说明 |
|---|---|---|
| `social.py` | `src/x2server/player/social.py` | 新增。`SocialReader`（持久层，表 `social_friends/social_applys/social_blacks/social_gifts/social_send_coins`）+ `SocialFriendService`（应答 `/FriendService.*`） |
| `ai_players.json` | `src/x2server/data/ai_players.json` | 新增。40 个人机的数据（`uid/hero/name/head/level/icon`） |

## 需要新增的协议（参考，字段号已按 IL2CPP 反汇编核对）

这些目前登记在本地 `src/x2server/messages/lobby.py` 里，接入时需要一并加：

```
# 请求
("SendFriendReq",     453, 454),
("SendFriendCoin",    434, 435),
("ReceiveFriendCoin", 436, 437),
("UpdateFriends",     449, 450),
("QueryChatFriendsTime", 672, 671),

"SendFriendReq":      (F(1,"playerid",    K.INT64, repeated=True),)
"SendFriendCoin":     (F(1,"playerid",    K.INT64, repeated=True),
                       F(2,"friendPoint", K.INT32, repeated=True))
"ReceiveFriendCoin":  (F(1,"playerid",    K.INT64, repeated=True),
                       F(2,"friendPoint", K.INT32, repeated=True))

# 回包
"SendFriendReq":      (F(1,"code",K.ENUM), F(2,"playerid",K.INT64, repeated=True))
"SendFriendCoin":     (F(1,"code",K.ENUM), F(2,"playerid",K.INT64, repeated=True))
"ReceiveFriendCoin":  (F(1,"code",K.ENUM), F(2,"playerid",K.INT64, repeated=True))
"UpdateFriends":      (F(1,"code",K.ENUM),)
"QueryChatFriendsTime": (F(1,"chatFriendsTime",K.MESSAGE, repeated=True),)
```

## 接入方式（需要在共享文件里加线）

主仓库里没有这些接线，需要手动加：

1. `src/x2server/player/lobby.py`：把上面几条协议登记进 `DELEGATED`，并把 `/FriendService.*`
   交给 `SocialFriendService` 应答。
2. `src/x2server/bootstrap/local_identity.py`：加 `_friend_http` 与 `/apply/queryPlayer`
   路由（客户端名片/推荐列表会走这个 HTTP 接口）。
3. `src/x2server/player/save_manager.py` / `login.py`：会话启动时把 `SocialReader` 挂上。

另外，「人机一起打社团镜域 / 蚀兽」的部分不在本目录，属于本地 `club.py` / `world_boss.py` 的改动，
如果需要我再单独整理。

## 已知限制

- 直接把 `social.py` 拷进去**不能跑**：它依赖上面的 DELEGATED 委托与 HTTP 路由接线，
  这几处是本地改过的共享文件，我没有一起放出来（会给主仓库带来大量无关 diff）。
- 人机名册是本地数据，不是从官方表还原的。
- 没有配套单测。

## 状态

本地单机环境下已实测可用（加好友、友情点收发、推荐列表、支援神格均正常）。
再次强调：**这只是一份参考实现，合不合、怎么合由维护者定。**
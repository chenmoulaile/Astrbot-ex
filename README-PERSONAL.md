# Astrb-RP · 个人用角色扮演平台

基于 **AstrBot v4.28.2** 二次开发的单机自用版本：保留 AstrBot 的全部能力与插件生态，
增加「角色卡 + 世界书 + 语料导入 + 提示词预览」的角色扮演引擎，并把 `E:\SublimeTextzip\Prompt`
里的 60 份 markdown 素材直接变成可选用的人格与可检索的世界知识库。

你最初提的每一件事，对应到哪里：

| 需求 | 实现方式 | 状态 |
|---|---|---|
| 拥有 AstrBot 的所有功能 | 本仓库就是 AstrBot 本体（v4.28.2），功能与上游一致 | ✅ |
| 兼容所有 AstrBot 插件 | 未改动插件加载器；新功能以「内置星 + core 模块」实现 | ✅ |
| 接入 QQ 机器人 / 设置 QQ 机器人 | AstrBot 平台层：OneBot v11（NapCat 等）与 QQ 官方机器人均可 | ✅ |
| 能和接入的 QQ 机器人聊天 | 网页端聊天 + QQ 收发消息 + 主动发送到指定 QQ/群 | ✅ |
| 内置 QQ、免密访问指定 QQ | 首次扫码后由协议端保持登录态，之后自动上线、不需密码（见下文风险说明） | ✅（机制说明见 §5） |
| 导入 `Prompt` 目录的 prompt | 一键导入：25 张角色卡（完美版/精简版双变体）+ 5 本世界书 + 178 条条目 | ✅ |
| 世界书 | 关键词触发的 lorebook 引擎：常驻/次级关键词/选择性逻辑/注入位置/优先级/token 预算/冷却/递归 | ✅ |
| 与机器人对话时套用这些设定 | 角色卡投影为 AstrBot 人格，世界书在 LLM 请求前注入，QQ 与网页端同一条链路 | ✅ |

---

## 1. 快速开始（Windows）

前置：`Python 3.12+`（仓库根目录 `.python-version` 已锁定 3.12，`uv` 会自动取用）、
`uv`、以及可选的 `Node.js 20+ / pnpm`（只有要自己构建网页界面时才需要）。

```bat
scripts\personal\setup.bat     :: 一次性：装依赖 + 构建并安装 WebUI
scripts\personal\start.bat     :: 启动
```

启动后控制台会打印**一次性自动生成的管理密码**，用默认用户名 `astrbot` 登录
`http://127.0.0.1:6185`，左侧栏出现「角色扮演」即成功。

配置大模型：`模型提供商` 页面加一个 OpenAI 兼容接口，或把 `base_url` 指向本地
`http://127.0.0.1:11434/v1`（Ollama，同样走 OpenAI 兼容协议）。AstrBot 原生支持两者。

导入你的 prompt：`角色扮演 → 导入语料`，目录填 `E:\SublimeTextzip\Prompt`，
先「扫描预览」再「执行导入」。

## 2. 角色扮演引擎做了什么

* **角色卡即人格。** 每张卡生成一个 AstrBot 人格（`rp_card_xxxx`），因此人格设定页、
  会话管理、任何平台的消息管道都能直接用它——不需要新的绑定机制。
* **提示块可开关。** 你素材里 `§1 最高信条 … §13 开场白`（精简版是 `一、…十、`）
  被解析成独立开关块，关掉某块会立即同步回人格提示词。
* **世界书按关键词注入。** 条目只在聊天文本命中关键词时进入上下文，并按
  `优先级 → 顺序` 受每本书的 token 预算约束；超出预算的条目会明确列出而不是静默丢弃。
* **注入位置可选。** 系统提示词之前（红线/译名口径这类必须始终生效的）、之后（普通资料），
  或插入历史消息指定深度（注入的消息带 `_no_save`，不会被写进数据库历史）。
* **预算内的取舍有规则。** 短小的常驻条目（红线、译名口径这类框架性要求）优先级最高；
  **超过 800 token 的常驻条目会主动让位给本轮真正命中的资料**，避免一本大对照表把上下文吃满；
  同级之间再按优先级与顺序排序，被挤掉的条目会在预览里明确列为「超预算跳过」。
* **可观测。** `提示词预览` 页走的是与真实请求完全相同的组装函数，能看到最终系统提示词、
  命中条目、命中关键词与 token 估算。

## 3. 你的语料是怎么被解析的

| 输入 | 解析结果 |
|---|---|
| `*_角色扮演SystemPrompt_无删减完美版.md` | 角色卡的 `full` 变体 |
| `*_角色扮演SystemPrompt_精简高质量版.md` | 角色卡的 `lite` 变体（默认启用，更省上下文） |
| `*_角色扮演SystemPrompt.md`（无版本后缀） | 该卡的 `base` 变体，不会覆盖上面两个 |
| `═` 分隔线包住的 `§N 标题` / `一、标题` | 一个提示块（标题与正文都保留） |
| 标题含「开场白」的段落里的 `**A · 场景**` + `>` 引用行 | 开场白列表，可作会话首条演出 |
| `*世界书*.md` / `*设定集*.md` | 一本世界书 |
| `## 第N章` / `###` 小节 | 一个条目（关键词取自标题与括号内别名） |
| 纯 `- **关键词**：说明` 列表 | 每个要点一个条目（世界书的最佳粒度） |
| 超长小节（>2400 字） | 按 `**小标题**` 拆分，避免单条超出预算 |

实测结果（2026-10-12，对 `E:\SublimeTextzip\Prompt` 的真实扫描）：
**51 份角色卡文本 → 25 张角色卡，5 本世界书，177 条条目**，行覆盖率 96.6%，
缺的部分只有刻意跳过的 `README.md` 与 `_创作规范.md`（它们是写作规范，不是设定资料）。

规则要点：

* `★`、`⚠` 之后的注解不进入关键词；括号内 `ゲヘナ / Gehenna，简中：歌赫娜学院；通称格黑娜`
  会展开成多个别名，`简中：`/`通称` 这类前缀会被剥掉。
* 标题含「译名/对照/自检/红线/使用约定」的条目自动标记为**常驻**。
* 卡与其同目录（或上层目录）的世界书自动绑定。
* 重复导入时 markdown 为准，但**保留**你手动改过的提示块开关、人格绑定、会话绑定、
  世界书预算与启用状态。

## 4. QQ 端指令

在任意已接入平台（QQ 私聊/群聊 @ 机器人，或网页聊天）可用：

| 指令 | 作用 |
|---|---|
| `/rp` | 当前角色卡、生效世界书、上次注入情况 |
| `/卡 [名字]` | 列出 / 绑定角色卡到当前会话 |
| `/变体 [lite\|full]` | 切换完美版 / 精简版 |
| `/块 [序号]` | 列出 / 开关提示块（立即同步人格） |
| `/世书 [序号]` | 列出 / 在本会话暂停某本世界书 |
| `/开场 [序号\|清]` | 选用开场白，清空历史后的第一条消息会带上它 |
| `/lore` | 上一次请求命中了哪些条目、命中词、token、被跳过原因 |
| `/导入 [目录]` | 管理员：扫描并导入语料，同步人格 |
| `/删卡 <名字>` | 管理员：删除角色卡及其人格 |

## 4.5 陪伴插件「我会永远陪着你」

`astrbot_plugin_private_companion`（作者 menglimi，v6.7.0，声明支持 AstrBot ≥4.22.0，本基线 4.28.2 满足）。
它是**持续型陪伴内核**：角色生活状态与日程、关系与亲密度账本、主动消息编排、群聊理解与观察、
记忆与备忘、衣柜/生图/表情、QQ 空间、新闻阅读，以及自带的可视化 Pages 管理页。实测导入后注册
**113 个处理器、21 个 `on_llm_request` 钩子、22 个 LLM 工具**。

安装 / 更新（全部落在 E 盘，不占 C 盘）：

```bat
scripts\personal\install-companion.bat            :: 首次安装
scripts\personal\install-companion.bat --update   :: 拉取上游新版本
```

要点：

* **不入库**：该插件仓库没有 LICENSE 文件，默认保留所有权利。所以本仓库只保存安装脚本，
  运行时 `git clone` 到 `vendor-cache/` 再复制到 `data/plugins/`。升级方便，也不会把未授权的
  第三方代码推成自己的项目。
* **依赖**：`chinese-calendar`、`lunarcalendar`、`markdown-it-py`（Pillow/aiohttp 已随 AstrBot 自带），
  由脚本装进 `data\site-packages`（AstrBot 会把它加入搜索路径）。
* **与 RP 引擎共存**：两边都挂 `on_llm_request`。钩子按 priority 从大到小执行，该插件的钩子分布在
  `+230000 ~ -260000`，因此本仓库的 `rp_engine` 固定为 `-1000000`（最后执行），保证世界书与开场白
  一定追加在最终请求里、不会被它先裁掉；两者都只**追加**系统提示词，不整体覆盖。有回归测试守着。
  想临时只留一个：`rp_engine.enable=false`，或用该插件配置里的「仅保留主动能力」开关。
* **首次使用**：面板「插件配置 → 我会永远陪着你」设置角色身份、目标用户/群、主动消息节奏与额度；
  私聊发 `陪伴 状态` 自检。
* **它会主动联网**：读取公开 RSS（solidot / BBC / Ars Technica / MIT TR / HN）、QQ 空间、B 站等，
  服务于它的新闻阅读与空间功能；未装 ComfyUI/生图扩展时相关能力自动关闭。不想用就在配置里关掉子功能。

## 4.6 磁盘策略：下载与缓存都在 E 盘

`setup.bat` 与 `install-companion.bat` 已在脚本内固定：

| 用途 | 位置 |
|---|---|
| uv / pip 缓存 | `E:\Astrb\.cache\uv`、`E:\Astrb\.cache\pip` |
| 安装临时目录 | `E:\Astrb\.cache\tmp` |
| 插件源码缓存 | `E:\Astrb\vendor-cache\` |
| 插件与运行时数据 | `E:\Astrb\data\`（含 `data\site-packages`） |
| pnpm 全局 store | `E:\.pnpm-store`（你机器上已是这个） |

AstrBot 本体不往 C 盘写数据，唯一例外是 `C:\Users\<你>\.astrbot\.installation_id`（36 字节安装标识）。
**注意：AstrBot Desktop 默认把全部数据放在 `C:\Users\<你>\.astrbot\`**，搬到 E 盘的办法见 §5.5。

## 5. QQ 接入：免密登录的真实机制

QQ 没有"不登录就能收发消息"的合法通道，所以这里的"免密"是这样实现的：

1. **首次登录一次**（扫码），协议端把 ticket / device 等登录态持久化在自己的数据目录；
2. 之后每次启动协议端都**自动上线，不再需要输入密码**；
3. `scripts\personal\qq-config.bat` 把 AstrBot 侧配置写好，`start.bat` 一键拉起；
4. AstrBot 作为**反向 WebSocket 服务端**监听，协议端连上来（断线会自动重连）。

两条可选路线：

* **OneBot v11（推荐，功能完整）**：NapCat / LLOneBot 等。支持收发主动消息、图片、
  表情、群管理事件，角色扮演体验最好。
  ```bat
  uv run python scripts\personal\make_qq_config.py
  ```
  它会写入平台配置并打印协议端要填的三项：`ws://127.0.0.1:6199/ws`、Access Token、类型「反向 WebSocket」。
  NapCat 的 Windows 用法：装好 QQ → 解压 `NapCat.Shell.zip` → 双击 `launcher.bat`
  （Win10 用 `launcher-win10.bat`）→ 扫码 → 打开 WebUI 填上面三项。
* **QQ 官方机器人**：用 AppID + AppSecret 换 access_token，本来就不需要账号密码，
  但接口能力与消息格式受限，且不支持上面的主动发送方式。

⚠️ **风险提示（必须知道）**：OneBot v11 属于非官方协议，违反腾讯服务条款，存在**封号**可能；
建议用专门的机器人小号，不要主力号。官方机器人路线没有这个风险，但功能受限。
本仓库默认监听 `0.0.0.0:6199` 与 `0.0.0.0:6185`，如果只是本机使用，建议在配置里把
`dashboard.host` / `ws_reverse_host` 改成 `127.0.0.1`。

## 5.5 与 AstrBot Desktop（桌面端）合并

桌面端内嵌自己的 core 运行时，数据目录默认 `C:\Users\<你>\.astrbot\`，插件放
`\.astrbot\data\plugins\`。代码里 `get_astrbot_root()` 的第一优先级是环境变量 `ASTRBOT_ROOT`，
**桌面端也服从它**，所以数据目录可以整体搬到 E 盘。按省事到彻底，三条路：

1. **只要陪伴插件**（建议先做这步）：它是标准 AstrBot 插件，直接装进桌面端数据目录，不用动它的 core：
   ```bat
   set "ASTRBOT_ROOT=E:\AstrbotDesktop"
   E:\Astrb\scripts\personal\install-companion.bat --root E:\AstrbotDesktop
   ```
   之后让桌面端在这个环境变量的下启动，它就把该目录当数据根（顺手解决 C 盘占用）。
2. **陪伴插件 + 我们的角色卡/世界书都要在桌面端用**：桌面端跑它自带的 core，不会加载本仓库对
   `astrbot/core`、`astrbot/dashboard` 的改动，所以「角色扮演」页面目前只有源码版有。
   根治办法是把 RP 引擎改造成**自包含插件 + 插件自带 Pages 页面**（AstrBot ≥4.22 支持，
   陪伴插件自己就是这么做的）：把 `astrbot/core/rp` 移进插件目录、`/api/rp` 改用插件注册的
   web API、前端页面改写成插件 Page。这是结构性改造，你说一句我就接着做。
3. **让桌面端直接跑这份 core**：桌面端是打包运行时（`ASTRBOT_DESKTOP_CLIENT=1`），会校验随包
   core 与 WebUI 版本匹配，替换内部 core 属非官方改法、每次升级会被覆盖，不建议。

数据迁移：把桌面端 `\.astrbot\data\` 里的 `cmd_config.json`、`data_v4.db`、`config/`、`plugins/`
复制到新的 `ASTRBOT_ROOT\data\` 再重启即可；面板密码与会话历史都跟着这两个文件走。

## 6. 为什么"所有功能 + 所有插件"能成立

没有重写任何 AstrBot 机制：

* 消息管道 9 个阶段、平台适配器、人格系统、知识库、Agent/MCP/技能、定时任务、
  内容安全、限速、t2i、语音转写等全部沿用上游实现；
* 世界书的注入发生在**上游就为插件预留的钩子**上（`@filter.on_llm_request()`，
  在人格与系统提示词组装完成之后、真正调用模型之前），因此 QQ、网页聊天、OpenAPI
  三条入口共用同一条注入链路，无需重复实现；
* 新增内容集中在下表，除 `app.py` 的 4 行接线外全部是**新文件**，方便日后 rebase 上游。

| 位置 | 内容 |
|---|---|
| `astrbot/core/rp/` | 引擎：模型、JSON 存储、匹配器、组装器、token 估算、markdown 导入器、人格桥接 |
| `astrbot/builtin_stars/rp_engine/` | 内置星：管道钩子 + QQ 端指令 + 插件配置项 |
| `astrbot/dashboard/services/rp_service.py`<br>`astrbot/dashboard/api/rp.py` | `/api/rp/*` 后端（受面板 JWT 保护） |
| `dashboard/src/views/RPPage.vue` + `views/rp/*` | 角色扮演页面（概览/角色卡/世界书/导入/预览） |
| `scripts/personal/` | setup / start / QQ 配置 / WebUI 安装脚本 |
| `tests/unit/test_rp_engine.py`<br>`tests/unit/test_rp_star.py` | 18 个新增测试（引擎 + 钩子集成） |

插件配置：`配置文件 → 插件配置 → rp_engine`
（总开关、是否把角色名计入扫描文本、全局注入 token 上限、无卡时是否应用全局世界书、
是否打印命中日志、`/导入` 默认目录）。

## 7. 验证情况

| 项目 | 结果 |
|---|---|
| `uv run pytest tests/unit/test_rp_engine.py tests/unit/test_rp_star.py` | 18 passed |
| `uv run pytest`（上游全量） | 2995 passed, 1 skipped, 6 failed |
| 上述 6 个失败 | 全部在 `test_dashboard_dist_resolution.py` / `test_updater_socks.py`，原因是本机存在已安装的 WebUI 资源；把 `data/dist` 与 `astrbot/dashboard/dist` 移走后重跑为 **56 passed**，非本次改动引入 |
| `ruff check` / `ruff format` | 全部通过 |
| `pnpm build`（含 `vue-tsc` 类型检查） | 通过 |
| 全新首启 | 清空 `data/` 后启动：插件无错加载、WebUI 正常服务、控制台打印初始密码、登录成功、导入产出 25 卡 / 5 书 / 177 条并同步 25 个人格、未登录访问 `/api/rp` 返回 401 |
| 界面 | 已在浏览器实测：登录、0 个缺失文案、五个分页齐全、角色卡详情显示 10 个提示块开关与开场白、预览页真实命中并渲染明细表 |

## 8. 已知限制（诚实说明）

1. token 数是**启发式估算**（中日韩字符≈1 token，拉丁约 4 字符≈1 token），不是精确值；
   没引入 tiktoken，是为了避免首次运行联网下载词表。
2. 完美版提示词最长约 19000 tokens（空崎阳奈），本地 8k 上下文模型会放不下；
   默认启用精简版（约 5k–8k），并按需关闭提示块或加大世界书预算。
3. 关键词抽取是启发式的：个别条目可能需要你在「世界书」页手动补关键词
   （导入报告列出每条的关键词，预览页可以即时验证是否命中）。
4. 「主动发送到平台」对 QQ 官方 API 平台无效（上游限制），页面已注明。
5. 会话绑定输入框要求完整的 UMO（`平台:会话类型:会话ID`）；日常更省事的做法是
   直接在 QQ 里发 `/卡 名字`，或用网页端「会话管理」给人格选会话。
6. 面板 `ja-JP` / `ru-RU` 的角色扮演文案暂用英文占位。
7. 非官方 QQ 协议的封号风险由使用者承担，建议专用小号。
8. 上游贡献规范要求：改动 WebUI 导航/页面后要同步 `docs/zh`、`docs/en` 的说明与截图。
   本站点文档我只写了这份 `README-PERSONAL.md`，截图在当前环境无法生成；若要提 PR 给上游，
   需要补 docs 页面的截图与条目。
9. 关键词命中依赖聊天文本里真的出现设定词。绑定角色卡时默认会把「角色名」也计入扫描文本
   （插件配置 `include_card_name`），这样以角色名作关键词的设定条目能稳定触发。

## 9. 与上游同步

```bat
基线提交 `chore: import AstrBot v4.28.2 upstream base` 的内容与上游 `3c7adafa1397` 的受版本控制文件一致
（上游 `.gitignore` 排除的 4 个生成物不在其中）。之后每个功能各一次提交，可用
`git diff 5625152 HEAD --stat` 看到全部二开改动（50 个文件，新增 6.7k 行，仅改动上游 59 行）。

```bat
set GIT_AUTHOR_NAME=Astrb-RP
set GIT_AUTHOR_EMAIL=astrb-rp@local
set GIT_COMMITTER_NAME=Astrb-RP
set GIT_COMMITTER_EMAIL=astrb-rp@local

git remote add upstream https://github.com/AstrBotDevs/AstrBot.git
git fetch upstream
git rebase upstream/master        :: 你的改动都在独立文件里，冲突面很小
scripts\personal\setup.bat        :: 重新构建界面
uv run pytest tests/unit/test_rp_engine.py tests/unit/test_rp_star.py
```

## 10. 推到 GitHub 与账号云同步

仓库已经是「一个上游基线提交 + 分层功能提交」，随时可推。但有三件事需要你定，我不替你决定：

* **凭据**：这台机器没有 `gh` CLI，`E:\Astrb` 也没有 remote。需要你的 GitHub 用户名 + 一种授权方式
  （`gh auth login`，或已在 Git 凭据管理器里登录的账号）。
* **可见性**：`data/` 已被 .gitignore 排除（角色卡、人格、面板密码、JWT、QQ token 都在里面），
  但本文档写了你的语料绝对路径。**建议先建私有仓库**；要公开我先把文档脱敏。
* **许可**：本仓库派生自 AstrBot（AGPL-3.0），公开需保留 LICENSE 与上游出处；
  陪伴插件无 LICENSE，只能靠安装脚本运行期拉取，不能进仓库。

云同步（不自建服务器的版本）：再开一个**私有**仓库只放 `data/rp/`、插件配置与人格导出，
配 `sync.bat`：`export` → `push`，另一台机器 `pull` → `import`。同步清单显式排除
`cmd_config.json`、`data/site-packages`、`*.db` 与任何 token。
要真正的账号体系（登录换 token、多端增量同步）就得有一台服务端，那是另一个项目，可以我做。

## 11. 本轮验证记录（可复现）

| 项目 | 命令 | 结果 |
|---|---|---|
| 引擎与钩子单测 | `uv run pytest tests/unit/test_rp_engine.py tests/unit/test_rp_star.py` | 19 passed（含钩子顺序回归） |
| 陪伴插件导入 | 以 `data/plugins` + `data/site-packages` 为路径导入其 `main.py` | 成功：113 处理器 / 21 个 LLM 请求钩子 / 22 个工具 |
| 安装器 | `scripts\personal\install-companion.bat` | 233 个条目装入，依赖落到 `data\site-packages` |
| 代码风格 | `uv run ruff check` / `ruff format --check` | 全部通过 |

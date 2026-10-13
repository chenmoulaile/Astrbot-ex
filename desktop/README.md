# Astrb-RP 桌面端

一个 Electron 外壳，把本仓库的 AstrBot 内核跑成本地桌面应用：托盘常驻、自动拉起内核、
内核挂掉自动重启、窗口直接显示面板（含「角色扮演」页面）。它不代理也不改写任何请求，
窗口就是访问 `http://127.0.0.1:<端口>`，所以聊天、插件、QQ 平台的行为与浏览器里完全一致。

## 用哪个目录跑

- 开发/日常使用：双击或在终端执行 `run.cmd`（等价 `npm install && npm start`）。
- 首次会问你项目目录；正常情况自动识别为仓库根（`desktop/` 的上一级）。识别错了点
  「选择项目目录」重选即可，选择记在
  `%APPDATA%\astrb-rp-desktop\astrb-rp.json`。
- 桌面端和 `scripts\personal\start.bat` **共用同一份数据**（角色卡、世界书、人格、插件、
  QQ 配置都在仓库的 `data/`），不存在两套数据要同步的问题。

## 与命令行版共存

同一份 `data/` 只能有一个内核实例在用。桌面端启动前请先关掉 `start.bat` 那个窗口，
否则会撞端口与配置文件。桌面端会自动挑一个空闲端口（默认优先 6185）。

## 打包成安装包

```bat
build.cmd            :: 产出 desktop\release\*.exe（NSIS 安装器）
npx electron-builder --win dir   :: 只要免安装目录 release\win-unpacked
```

下载与缓存全部钉在 `E:\Astrb\.cache`（npm / electron / electron-builder 各自子目录），
不写 C 盘。安装包未做代码签名，Windows SmartScreen 会提示「未知发布者」，属正常。

## 已知限制

1. **需要登录一次**：面板用户名 `astrbot`，密码是内核首次启动生成的那个（命令行首启日志里
   打印过；忘了就在仓库根执行 `uv run python main.py --reset-password` 重新生成）。
   官方桌面端用的自动登录依赖 `ASTRBOT_DESKTOP_MANAGED=1`，而那个模式会让内核
   **拒用 `data/dist`**——角色扮演页面就装在里面，所以这里刻意不开自动登录。
2. 托盘图标使用 `desktop/assets/icon.png`；没有该文件时退化为空图标（不影响功能）。
3. 内核日志只保留最近 400 行进启动页；完整日志仍在 `data/logs/astrbot.log`。
4. 自动重启上限 5 次，避免配置错误时无限拉起。

## 自检

```bat
cd desktop
npm run smoke
```

在 `E:\Astrb\.cache` 下开一个**隔离的一次性数据目录**真实启动内核，检查：首页可访问、
`/api/rp` 已注册且未登录返回 401、面板 OpenAPI 正常、`rp_engine` 内置星加载、无插件加载失败。
不会干扰你正在运行的实例。

/**
 * Astrb-RP desktop shell.
 *
 * Boots the AstrBot backend that lives in the repository checkout, shows its
 * WebUI in a native window, keeps running in the tray, and restarts the core
 * when it dies. No request is proxied or rewritten: the window talks to the
 * local dashboard directly, so the roleplay pages, chat and plugins behave
 * exactly as they do in the browser.
 */
'use strict';

const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const { app, BrowserWindow, Menu, dialog, ipcMain, nativeImage, shell, Tray } = require('electron');

const { Backend, pickPort, waitForHealth } = require('./backend');
const settingsStore = require('./settings');

const state = {
  win: null,
  tray: null,
  backend: null,
  settings: { ...settingsStore.DEFAULTS },
  port: 0,
  quitting: false,
  restarts: 0,
  log: [],
};

const settingsFile = () => path.join(app.getPath('userData'), 'astrb-rp.json');

/**
 * Append a line to the in-memory boot log and mirror it to the console.
 *
 * @param {string} line Message text.
 * @returns {void}
 */
function log(line) {
  const stamp = new Date().toISOString().slice(11, 19);
  state.log.push(`[${stamp}] ${line}`);
  if (state.log.length > 400) state.log.shift();
  console.log(`[desktop] ${line}`);
  if (state.win && !state.win.isDestroyed()) {
    state.win.webContents.send('boot-log', state.log.slice(-120));
  }
}

/**
 * Make sure a locally built WebUI is installed where the core will serve it.
 *
 * @param {string} repoRoot Repository root.
 * @returns {void}
 */
function ensureWebui(repoRoot) {
  const bundled = path.join(repoRoot, 'dashboard', 'dist', 'index.html');
  if (!fs.existsSync(bundled)) {
    log('未发现本地构建的界面（dashboard/dist），首次启动会下载上游界面，角色扮演页面可能缺失');
    return;
  }
  const served = path.join(repoRoot, 'data', 'dist', 'assets');
  const hasPages = (() => {
    try {
      return fs.readdirSync(served).some((name) => name.startsWith('RPPage'));
    } catch {
      return false;
    }
  })();
  if (hasPages) return;
  log('安装本地构建的界面到 data/dist 与 astrbot/dashboard/dist ...');
  const res = spawnSync('uv', ['run', 'python', 'scripts/personal/install_webui.py'], {
    cwd: repoRoot,
    encoding: 'utf8',
    windowsHide: true,
  });
  for (const line of String(res.stdout || '').split(/\r?\n/)) if (line.trim()) log(line.trim());
  if (res.status !== 0) log(`界面安装失败：${String(res.stderr || '').slice(0, 200)}`);
}

/**
 * Push the current status to the window.
 *
 * @param {object} extra Fields merged into the status payload.
 * @returns {void}
 */
function sendStatus(extra = {}) {
  if (state.win && !state.win.isDestroyed()) {
    state.win.webContents.send('status', {
      port: state.port,
      repoRoot: state.settings.repoRoot,
      running: Boolean(state.backend && state.backend.running),
      ...extra,
    });
  }
}

/**
 * Stop the backend if one is attached.
 *
 * @returns {Promise<void>} Resolves when stopped.
 */
async function stopBackend() {
  if (state.backend) await state.backend.stop();
  state.backend = null;
}

/**
 * Start the core and load its WebUI once it answers.
 *
 * @returns {Promise<void>} Resolves after the window has been pointed at the UI.
 */
async function startBackend() {
  if (!settingsStore.looksLikeRepo(state.settings.repoRoot)) {
    log('还没有选择 AstrBot 项目目录');
    sendStatus({ error: '需要先选择 Astrb-RP 项目目录' });
    return;
  }
  ensureWebui(state.settings.repoRoot);
  state.port = await pickPort(state.settings.port || 6185);
  log(`使用端口 ${state.port}`);
  await stopBackend();
  state.backend = new Backend({
    cwd: state.settings.repoRoot,
    pythonCmd: state.settings.uvCmd || 'uv',
    pythonArgs: ['run', 'python', 'main.py'],
    port: state.port,
    env: settingsStore.backendEnv(state.settings),
    onLog: (line) => {
      if (/Traceback|Error|错误：/.test(line)) log(line);
    },
    onExit: async (code) => {
      if (state.quitting) return;
      sendStatus({ error: `内核已退出 (code=${code})` });
      if (state.settings.autoRestart && state.restarts < 5) {
        state.restarts += 1;
        log(`5 秒后自动重启内核（第 ${state.restarts} 次）`);
        setTimeout(startBackend, 5000);
      }
    },
  });
  state.backend.start();
  sendStatus({ phase: 'booting' });
  try {
    await waitForHealth(state.port, { onLog: log });
  } catch (error) {
    log(String(error.message));
    sendStatus({ error: error.message });
    return;
  }
  state.restarts = 0;
  sendStatus({ phase: 'ready' });
  if (state.win && !state.win.isDestroyed()) {
    await state.win.loadURL(`http://127.0.0.1:${state.port}/`);
  }
}

/**
 * Create the main window with the boot screen.
 *
 * @returns {void}
 */
function createWindow() {
  state.win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 560,
    backgroundColor: '#101418',
    title: 'Astrb-RP',
    icon: appIcon(),
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  state.win.loadFile(path.join(__dirname, 'loading.html'));
  state.win.webContents.on('did-finish-load', () => {
    const url = state.win.webContents.getURL();
    log(url.startsWith('file:') ? '启动页已显示' : `界面已载入：${url}`);
  });
  state.win.webContents.on('did-fail-load', (_event, code, description) => {
    if (code === -3) return; // aborted, usual when reloading
    log(`页面加载失败：${code} ${description}`);
    state.win.loadFile(path.join(__dirname, 'loading.html'));
    sendStatus({ error: '界面加载失败，正在重试' });
  });
  state.win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
  state.win.on('close', (event) => {
    if (!state.quitting && state.settings.closeToTray) {
      event.preventDefault();
      state.win.hide();
      log('已隐藏到托盘（托盘菜单里可退出）');
    }
  });
}

/**
 * Load the app icon, falling back to a blank image if assets are missing.
 *
 * @returns {Electron.NativeImage} Image usable by the window and the tray.
 */
function appIcon() {
  const file = path.join(__dirname, '..', 'assets', 'icon.png');
  const image = nativeImage.createFromPath(file);
  return image.isEmpty() ? nativeImage.createEmpty() : image;
}

/**
 * Build the tray menu used to control the core.
 *
 * @returns {void}
 */
function createTray() {
  state.tray = new Tray(appIcon());
  state.tray.setToolTip('Astrb-RP');
  state.tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: '显示窗口', click: () => state.win.show() },
      { type: 'separator' },
      { label: '重启内核', click: () => startBackend() },
      { label: '打开数据目录', click: () => shell.openPath(path.join(state.settings.repoRoot, 'data')) },
      { label: '打开面板（浏览器）', click: () => shell.openExternal(`http://127.0.0.1:${state.port}`) },
      { type: 'separator' },
      {
        label: '退出',
        click: () => {
          state.quitting = true;
          app.quit();
        },
      },
    ])
  );
  state.tray.on('click', () => state.win.show());
}

/**
 * Register renderer IPC handlers.
 *
 * @returns {void}
 */
function registerIpc() {
  ipcMain.handle('get-state', () => ({
    settings: state.settings,
    port: state.port,
    log: state.log.slice(-120),
    running: Boolean(state.backend && state.backend.running),
  }));
  ipcMain.handle('restart-backend', () => startBackend());
  ipcMain.handle('open-dashboard', () => shell.openExternal(`http://127.0.0.1:${state.port}`));
  ipcMain.handle('choose-repo', async () => {
    const picked = await dialog.showOpenDialog(state.win, {
      title: '选择 Astrb-RP 项目目录',
      properties: ['openDirectory'],
      defaultPath: state.settings.repoRoot || app.getPath('documents'),
    });
    if (picked.canceled || !picked.filePaths.length) return { ok: false };
    const dir = picked.filePaths[0];
    if (!settingsStore.looksLikeRepo(dir)) {
      dialog.showErrorBox('目录不对', '该目录下没有 main.py / pyproject.toml / astrbot，选错啦。');
      return { ok: false };
    }
    state.settings.repoRoot = dir;
    settingsStore.save(settingsFile(), state.settings);
    log(`项目目录已设为 ${dir}`);
    await startBackend();
    return { ok: true };
  });
}

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  const loaded = settingsStore.load(settingsFile());
  state.settings = loaded.settings;
  if (!loaded.repoFound) log('未找到项目目录，请在下方手动选择');
  registerIpc();
  createWindow();
  try {
    createTray();
  } catch (error) {
    log(`托盘创建失败（不影响使用）：${error.message}`);
  }
  if (loaded.repoFound) await startBackend();
});

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (state.win) {
      state.win.show();
      state.win.focus();
    }
  });
}

app.on('window-all-closed', () => {
  if (!state.settings.closeToTray) app.quit();
});

app.on('before-quit', async () => {
  state.quitting = true;
  await stopBackend();
});

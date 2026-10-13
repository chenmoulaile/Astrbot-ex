/**
 * Headless check of the desktop shell's backend supervision.
 *
 * Boots the real core in a throwaway ASTRBOT_ROOT so it can never collide with
 * an already running instance, then asserts that it becomes healthy and that
 * the roleplay API is reachable and protected.
 *
 * Usage:
 *   npm run smoke        (from desktop/)
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { Backend, pickPort, waitForHealth, get } = require('../src/backend');

const REPO = path.resolve(__dirname, '..', '..');

/**
 * Recursively remove a directory, ignoring failures.
 *
 * @param {string} dir Path to delete.
 * @returns {void}
 */
function rmrf(dir) {
  try {
    fs.rmSync(dir, { recursive: true, force: true });
  } catch {
    /* best effort */
  }
}

async function main() {
  // Keep scratch data on the project drive; the system drive is nearly full.
  const scratch = path.join(REPO, '.cache');
  fs.mkdirSync(scratch, { recursive: true });
  const root = fs.mkdtempSync(path.join(scratch, 'smoke-'));
  const port = await pickPort(0);
  const seen = [];
  const backend = new Backend({
    cwd: REPO,
    pythonCmd: 'uv',
    pythonArgs: ['run', 'python', 'main.py'],
    port,
    env: { ASTRBOT_ROOT: root },
    onLog: (line) => seen.push(line),
  });

  const checks = [];
  const expect = (name, ok, detail = '') => {
    checks.push({ name, ok, detail });
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`);
  };

  try {
    backend.start();
    await waitForHealth(port, { timeoutMs: 240000, onLog: (line) => seen.push(line) });

    const index = await get(port, '/');
    expect('首页可访问', index.status === 200 && index.body.includes('<div id="app"'), `HTTP ${index.status}`);

    const rp = await get(port, '/api/rp/overview');
    expect('/api/rp 已注册且受登录保护', rp.status === 401, `HTTP ${rp.status}`);

    const v1 = await get(port, '/api/v1/openapi.json');
    expect('面板 OpenAPI 正常', v1.status === 200, `HTTP ${v1.status}`);

    const joined = seen.join('\n');
    expect('rp_engine 内置星加载成功', joined.includes('Loading plugin rp_engine'));
    expect(
      '无插件加载失败',
      !joined.includes('Failed to load plugin'),
      joined.split('\n').filter((l) => l.includes('Failed')).slice(0, 2).join(' | ')
    );
  } finally {
    await backend.stop();
    rmrf(root);
  }

  const failed = checks.filter((c) => !c.ok);
  console.log(`\n${checks.length - failed.length}/${checks.length} checks passed`);
  if (failed.length) {
    console.log('--- backend log tail ---');
    console.log(seen.slice(-25).join('\n'));
    process.exit(1);
  }
}

main().catch((error) => {
  console.error('SMOKE ERROR:', error);
  process.exit(1);
});

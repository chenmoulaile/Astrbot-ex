/**
 * Make sure the Electron binary exists, and keep its download cache off C:.
 *
 * Electron 44 no longer ships a postinstall hook (it exposes
 * `install-electron` instead), so package managers will not fetch the binary by
 * themselves. @electron/get also ignores ELECTRON_CACHE and defaults to
 * `%LOCALAPPDATA%\electron\Cache`, which would fill the system drive; the only
 * variable it honors is `electron_config_cache`, set here as an absolute path.
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const DESKTOP = path.resolve(__dirname, '..');
const CACHE = path.resolve(DESKTOP, '..', '.cache', 'electron');
const BINARY = path.join(DESKTOP, 'node_modules', 'electron', 'dist', 'electron.exe');

for (const key of ['electron_config_cache', 'ELECTRON_CACHE', 'electron_builder_binaries_cache']) {
  process.env[key] = CACHE;
}
fs.mkdirSync(CACHE, { recursive: true });

if (fs.existsSync(BINARY)) {
  console.log(`electron binary present: ${BINARY}`);
  process.exit(0);
}

console.log('downloading electron binary (cache: ' + CACHE + ') ...');
const result = spawnSync(process.execPath, ['node_modules/electron/install.js'], {
  cwd: DESKTOP,
  stdio: 'inherit',
  env: process.env,
});
if (result.status !== 0 || !fs.existsSync(BINARY)) {
  console.error('electron binary download failed');
  process.exit(1);
}
console.log('electron ready');

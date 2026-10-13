/**
 * Desktop shell settings, persisted outside the source tree.
 *
 * The shell wraps a source checkout of this repository rather than bundling a
 * private copy of the core, so the desktop app and `start.bat` share the same
 * cards, world books, personas and plugins.
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const DEFAULTS = {
  repoRoot: '',
  port: 6185,
  closeToTray: true,
  autoRestart: true,
  shareDataRoot: true,
  dataRoot: '',
  uvCmd: 'uv',
};

/**
 * Decide whether a directory looks like an AstrBot checkout.
 *
 * @param {string} dir Candidate root.
 * @returns {boolean} True when the entry point and project file are present.
 */
function looksLikeRepo(dir) {
  if (!dir) return false;
  try {
    return (
      fs.existsSync(path.join(dir, 'main.py')) &&
      fs.existsSync(path.join(dir, 'pyproject.toml')) &&
      fs.existsSync(path.join(dir, 'astrbot'))
    );
  } catch {
    return false;
  }
}

/**
 * Locate the repository that owns this desktop shell.
 *
 * @returns {string} Absolute candidate path.
 */
function guessRepoRoot() {
  // <repo>/desktop/src -> <repo>
  return path.resolve(__dirname, '..', '..');
}

/**
 * Load persisted settings, filling in defaults and validating the repo path.
 *
 * @param {string} file Settings file inside userData.
 * @returns {{settings: object, repoFound: boolean}} Effective settings.
 */
function load(file) {
  const settings = { ...DEFAULTS };
  try {
    Object.assign(settings, JSON.parse(fs.readFileSync(file, 'utf8')));
  } catch {
    // first run: no file yet
  }
  let repoFound = looksLikeRepo(settings.repoRoot);
  if (!repoFound) {
    const guess = guessRepoRoot();
    if (looksLikeRepo(guess)) {
      settings.repoRoot = guess;
      repoFound = true;
    } else {
      settings.repoRoot = '';
    }
  }
  return { settings, repoFound };
}

/**
 * Persist settings.
 *
 * @param {string} file Settings path.
 * @param {object} settings Values to write.
 * @returns {void}
 */
function save(file, settings) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const trimmed = {};
  for (const key of Object.keys(DEFAULTS)) trimmed[key] = settings[key];
  fs.writeFileSync(file, JSON.stringify(trimmed, null, 2), 'utf8');
}

/**
 * Build the environment passed to the backend process.
 *
 * @param {object} settings Effective settings.
 * @returns {Record<string,string>} Extra env vars.
 */
function backendEnv(settings) {
  const env = {};
  if (!settings.shareDataRoot && settings.dataRoot) env.ASTRBOT_ROOT = settings.dataRoot;
  // Never set ASTRBOT_DESKTOP_MANAGED: the core then rejects <data>/dist,
  // which is where the roleplay WebUI is installed.
  return env;
}

module.exports = { DEFAULTS, load, save, looksLikeRepo, guessRepoRoot, backendEnv };

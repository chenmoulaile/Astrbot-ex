/**
 * Supervise the local AstrBot backend process.
 *
 * The desktop shell deliberately starts the core in normal mode: setting
 * ASTRBOT_DESKTOP_MANAGED=1 makes the core refuse <data>/dist, and the roleplay
 * pages live in that dist. Readiness is probed on an endpoint the dashboard
 * exempts from authentication.
 */
'use strict';

const { spawn } = require('node:child_process');
const http = require('node:http');
const net = require('node:net');

const HEALTH_PATH = '/api/stat/start-time';

/**
 * Pick a TCP port that is free, preferring the configured one.
 *
 * @param {number} preferred Port the user asked for.
 * @returns {Promise<number>} The port to use.
 */
function pickPort(preferred) {
  return new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once('error', () => {
      const fallback = net.createServer();
      fallback.once('error', reject);
      fallback.listen(0, '127.0.0.1', () => {
        const port = fallback.address().port;
        fallback.close(() => resolve(port));
      });
    });
    probe.listen(preferred, '127.0.0.1', () => {
      // preferred may be 0, so report the port actually bound, not the request.
      const port = probe.address().port;
      probe.close(() => resolve(port));
    });
  });
}

/**
 * Issue a loopback GET against the running backend.
 *
 * @param {number} port Backend port.
 * @param {string} path Request path.
 * @returns {Promise<{status: number, body: string}>} Response summary.
 */
function get(port, path) {
  return new Promise((resolve, reject) => {
    const req = http.get(
      { host: '127.0.0.1', port, path, timeout: 4000 },
      (res) => {
        let body = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => {
          if (body.length < 20000) body += chunk;
        });
        res.on('end', () => resolve({ status: res.statusCode, body }));
      }
    );
    req.on('error', reject);
    req.on('timeout', () => req.destroy(new Error('timeout')));
  });
}

/**
 * Wait until the backend answers, or give up.
 *
 * @param {number} port Backend port.
 * @param {object} [options] Extra options.
 * @param {number} [options.timeoutMs] Overall budget.
 * @param {(line: string) => void} [options.onLog] Sink for progress lines.
 * @returns {Promise<void>} Resolves when healthy.
 */
async function waitForHealth(port, { timeoutMs = 180000, onLog = () => {} } = {}) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const res = await get(port, HEALTH_PATH);
      if (res.status === 200) {
        onLog(`后端已就绪 (HTTP ${res.status})`);
        return;
      }
    } catch (error) {
      lastError = error;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`后端启动超时：${lastError ? lastError.message : 'no response'}`);
}

/**
 * A running (or stopped) backend child process.
 */
class Backend {
  /**
   * @param {object} options Launch configuration.
   * @param {string} options.cwd AstrBot repository root.
   * @param {string} options.pythonCmd Executable to launch.
   * @param {string[]} options.pythonArgs Arguments for that executable.
   * @param {number} options.port Dashboard port.
   * @param {Record<string,string>} [options.env] Extra environment variables.
   * @param {(line: string) => void} [options.onLog] Backend output sink.
   * @param {(code: number|null) => void} [options.onExit] Exit callback.
   */
  constructor({ cwd, pythonCmd, pythonArgs, port, env = {}, onLog = () => {}, onExit = () => {} }) {
    this.cwd = cwd;
    this.pythonCmd = pythonCmd;
    this.pythonArgs = pythonArgs;
    this.port = port;
    this.env = env;
    this.onLog = onLog;
    this.onExit = onExit;
    this.child = null;
  }

  /**
   * Spawn the backend and pipe its output into the log sink.
   *
   * @returns {void}
   */
  start() {
    if (this.child) return;
    this.onLog(`启动内核：${this.pythonCmd} ${this.pythonArgs.join(' ')}  (cwd=${this.cwd})`);
    this.child = spawn(this.pythonCmd, this.pythonArgs, {
      cwd: this.cwd,
      // Defaults first so an explicit caller or shell override still wins.
      env: {
        PYTHONIOENCODING: 'utf-8',
        PYTHONUTF8: '1',
        ...process.env,
        DASHBOARD_PORT: String(this.port),
        ...this.env,
      },
      windowsHide: true,
    });
    const absorb = (stream) => {
      stream.setEncoding('utf8');
      let pending = '';
      stream.on('data', (chunk) => {
        pending += chunk;
        const lines = pending.split(/\r?\n/);
        pending = lines.pop() ?? '';
        for (const line of lines) if (line.trim()) this.onLog(line.trim());
      });
    };
    absorb(this.child.stdout);
    absorb(this.child.stderr);
    this.child.on('error', (error) => {
      this.onLog(`进程启动失败：${error.message}`);
      this.child = null;
    });
    this.child.on('exit', (code) => {
      this.onLog(`内核退出，code=${code}`);
      this.child = null;
      this.onExit(code);
    });
  }

  /**
   * Stop the backend, killing its whole process tree on Windows.
   *
   * @returns {Promise<void>} Resolves once the process is gone.
   */
  async stop() {
    const child = this.child;
    if (!child) return;
    this.child = null;
    await new Promise((resolve) => {
      let settled = false;
      const done = () => {
        if (!settled) {
          settled = true;
          resolve();
        }
      };
      child.once('exit', done);
      setTimeout(done, 6000);
      if (process.platform === 'win32') {
        const killer = spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true });
        killer.on('error', () => child.kill('SIGTERM'));
      } else {
        child.kill('SIGTERM');
        setTimeout(() => child.kill('SIGKILL'), 4000);
      }
    });
  }

  /**
   * @returns {boolean} Whether a child process is currently attached.
   */
  get running() {
    return Boolean(this.child);
  }
}

module.exports = { Backend, pickPort, get, waitForHealth, HEALTH_PATH };

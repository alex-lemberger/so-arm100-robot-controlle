'use strict';
const http = require('http');
const { spawn } = require('child_process');
const path = require('path');
const os = require('os');

const PORT = Number(process.env.SIM_LAUNCHER_PORT ?? 3001);
const SIM_DIR = path.join(os.homedir(), 'handwerk-robot-sim');
const MJPYTHON = path.join(SIM_DIR, '.venv/bin/mjpython');
const HTDP_DIR = process.env.HTDP_DIR ?? path.join(os.homedir(), 'human-task-dataset-pipeline');
const HTDP_PORT = Number(process.env.HTDP_PORT ?? 8000);

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': 'http://localhost:4200',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Content-Type': 'application/json',
};

let simProc = null;
let htdpProc = null;

function killSim() {
  if (simProc) {
    simProc.kill('SIGTERM');
    simProc = null;
  }
}

function killHtdp() {
  if (htdpProc) {
    // Spawned detached (own process group) so we can kill uv + its python child too.
    try { process.kill(-htdpProc.pid, 'SIGTERM'); } catch { /* already gone */ }
    htdpProc = null;
  }
}

const server = http.createServer((req, res) => {
  Object.entries(CORS_HEADERS).forEach(([k, v]) => res.setHeader(k, v));

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  if (req.method === 'POST' && req.url === '/sim/start') {
    killSim();
    try {
      simProc = spawn(MJPYTHON, ['sim/ws_server.py', '--model', 'h1_hand'], {
        cwd: SIM_DIR,
        stdio: 'inherit',
      });
      simProc.on('exit', () => { simProc = null; });
      res.writeHead(200);
      res.end(JSON.stringify({ ok: true, pid: simProc.pid }));
    } catch (err) {
      res.writeHead(500);
      res.end(JSON.stringify({ ok: false, error: String(err.message) }));
    }
    return;
  }

  if (req.method === 'POST' && req.url === '/sim/stop') {
    killSim();
    res.writeHead(200);
    res.end(JSON.stringify({ ok: true }));
    return;
  }

  if (req.method === 'POST' && req.url === '/htdp/start') {
    killHtdp();
    try {
      // `uv sync` first (idempotent, fast once installed) then the read/job-runner server.
      // detached so the whole `uv -> python` group can be signalled on stop.
      htdpProc = spawn(
        'bash',
        ['-lc', `uv sync --extra serve && uv run htdp serve --port ${HTDP_PORT}`],
        { cwd: HTDP_DIR, stdio: 'inherit', detached: true },
      );
      htdpProc.on('exit', () => { htdpProc = null; });
      res.writeHead(200);
      res.end(JSON.stringify({ ok: true, pid: htdpProc.pid }));
    } catch (err) {
      res.writeHead(500);
      res.end(JSON.stringify({ ok: false, error: String(err.message) }));
    }
    return;
  }

  if (req.method === 'POST' && req.url === '/htdp/stop') {
    killHtdp();
    res.writeHead(200);
    res.end(JSON.stringify({ ok: true }));
    return;
  }

  res.writeHead(404);
  res.end(JSON.stringify({ error: 'Not found' }));
});

process.on('exit', () => { killSim(); killHtdp(); });
process.on('SIGINT', () => { killSim(); killHtdp(); process.exit(0); });
process.on('SIGTERM', () => { killSim(); killHtdp(); process.exit(0); });

server.listen(PORT, () => console.log(`[sim-launcher] http://localhost:${PORT}`));
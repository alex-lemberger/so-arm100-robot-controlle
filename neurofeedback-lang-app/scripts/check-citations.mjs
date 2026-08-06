#!/usr/bin/env node
// Citation enforcement gate (AGENTS.md Operating Principle #12).
//
// Scans review/analysis/spec markdown and rejects citations that do not
// resolve to verifiable ground truth:
//   1. file:line refs (path.ext#L12-20 / path.ext:12 / file://.../path.ext#L12)
//      -> the file must exist and the line(s) must be within range.
//   2. "Rule #N" / "Principle #N" refs -> N must be a real numbered item in
//      AGENTS.md (its lists max out at 12; #27/#30/#43/#115 are fabricated).
//   3. "p.<n>" / "page <n>" refs -> markdown has no pages; always invalid.
//
// A weak model cannot reliably check its own citations; this gate does it for
// it. Escape hatches: `<!-- cite-check: ignore -->` on a line, or
// `<!-- cite-check: ignore-file -->` anywhere in a file.
//
// Exit 0 = all citations resolve. Exit 1 = at least one is unverifiable.

import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { join, resolve, dirname, isAbsolute, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REPO_NAME = REPO_ROOT.split(sep).pop();
const SCAN_DIRS = ['specs', 'analyses', 'plans'];
const CODE_EXT = 'ts|tsx|js|mjs|html|scss|css|json|md';

// --- build the set of valid AGENTS.md rule numbers from the doc itself ---
function validRuleNumbers() {
  const set = new Set();
  const agents = join(REPO_ROOT, 'AGENTS.md');
  if (!existsSync(agents)) return set;
  for (const line of readFileSync(agents, 'utf8').split('\n')) {
    const m = line.match(/^\s*(?:###\s*)?(\d+)\.\s+\S/);
    if (m) set.add(Number(m[1]));
  }
  return set;
}

// --- collect *.md files under the scan dirs ---
function markdownFiles() {
  const out = [];
  const walk = (dir) => {
    if (!existsSync(dir)) return;
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (entry.isFile() && entry.name.endsWith('.md')) out.push(p);
    }
  };
  for (const d of SCAN_DIRS) walk(join(REPO_ROOT, d));
  return out;
}

const lineCountCache = new Map();
function lineCount(absPath) {
  if (lineCountCache.has(absPath)) return lineCountCache.get(absPath);
  const n = readFileSync(absPath, 'utf8').split('\n').length;
  lineCountCache.set(absPath, n);
  return n;
}

// Turn a cited path (possibly file:// or absolute machine path) into a
// repo-relative path, or null if it cannot be located in this repo.
function toRepoRelative(raw) {
  let p = raw;
  if (p.startsWith('file://')) {
    try { p = fileURLToPath(p.split('#')[0]); } catch { return null; }
  }
  p = p.split('#')[0];
  if (isAbsolute(p)) {
    if (p.startsWith(REPO_ROOT + sep)) return p.slice(REPO_ROOT.length + 1);
    const marker = sep + REPO_NAME + sep;
    const idx = p.indexOf(marker);
    if (idx !== -1) return p.slice(idx + marker.length);
    return null; // absolute path we cannot anchor to this repo
  }
  return p;
}

function checkFileLine(rel, startLine, endLine, ctx, violations) {
  if (rel == null) {
    violations.push({ ...ctx, reason: 'absolute path is not anchored in this repo (use a repo-relative path)' });
    return;
  }
  const abs = join(REPO_ROOT, rel);
  if (!existsSync(abs) || !statSync(abs).isFile()) {
    violations.push({ ...ctx, reason: `file not found: ${rel}` });
    return;
  }
  const total = lineCount(abs);
  const start = Number(startLine);
  const end = endLine == null ? start : Number(endLine);
  if (start < 1 || end > total || start > end) {
    violations.push({ ...ctx, reason: `line ${startLine}${endLine ? '-' + endLine : ''} out of range (${rel} has ${total} lines)` });
  }
}

const RE_FILELINE_HASH = new RegExp(`((?:file://)?[\\w./~+-]+\\.(?:${CODE_EXT}))#L(\\d+)(?:[-–]L?(\\d+))?`, 'g');
const RE_FILELINE_COLON = new RegExp(`(?<![\\w/])([\\w./~+-]+\\.(?:${CODE_EXT})):(\\d+)(?:-(\\d+))?\\b`, 'g');
const RE_RULE = /(?:Rule|Principle)\s*#\s*(\d+)/gi;
const RE_PAGE = /(\bp\.\s*\d+|\bpage\s+\d+\b)/gi;

function scan(file, validRules) {
  const violations = [];
  const lines = readFileSync(file, 'utf8').split('\n');
  const relFile = file.slice(REPO_ROOT.length + 1);
  if (lines.some((l) => l.includes('cite-check: ignore-file'))) return violations;

  let inFence = false;
  lines.forEach((line, i) => {
    if (/^\s*```/.test(line)) { inFence = !inFence; return; }
    if (inFence) return;
    if (line.includes('cite-check: ignore')) return;
    const at = { file: relFile, line: i + 1 };

    for (const m of line.matchAll(RE_FILELINE_HASH)) {
      checkFileLine(toRepoRelative(m[1]), m[2], m[3], { ...at, cite: m[0] }, violations);
    }
    for (const m of line.matchAll(RE_FILELINE_COLON)) {
      if (/^https?:/i.test(m[0])) continue;
      checkFileLine(toRepoRelative(m[1]), m[2], m[3], { ...at, cite: m[0] }, violations);
    }
    for (const m of line.matchAll(RE_RULE)) {
      const n = Number(m[1]);
      if (!validRules.has(n)) {
        violations.push({ ...at, cite: m[0], reason: `AGENTS.md has no ${m[0]} (valid: 1-${Math.max(...validRules)})` });
      }
    }
    for (const m of line.matchAll(RE_PAGE)) {
      violations.push({ ...at, cite: m[1].trim(), reason: 'markdown has no pages — cite by file:line or heading text' });
    }
  });
  return violations;
}

// --- run ---
const validRules = validRuleNumbers();
const files = markdownFiles();
let total = 0;
const byFile = new Map();

for (const f of files) {
  const v = scan(f, validRules);
  if (v.length) { byFile.set(f, v); total += v.length; }
}

if (total === 0) {
  console.log(`✓ citation gate: ${files.length} file(s) scanned, all citations resolve.`);
  process.exit(0);
}

console.error(`✗ citation gate: ${total} unverifiable citation(s) in ${byFile.size} file(s).\n`);
for (const [, v] of byFile) {
  console.error(`${v[0].file}`);
  for (const x of v) console.error(`  L${x.line}: "${x.cite}" — ${x.reason}`);
  console.error('');
}
console.error('Every citation must resolve to a real file:line, a real AGENTS.md rule number, or quoted heading text.');
console.error('Fix or remove the citation; use "<!-- cite-check: ignore -->" only for a deliberate non-citation.');
process.exit(1);

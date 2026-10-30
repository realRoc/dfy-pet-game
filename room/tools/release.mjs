#!/usr/bin/env node
// Copies the single-file build to ../content/room/index.html, which the
// pet's local room server serves (the pet's users may not have node, and dist/ is
// ignored). Also writes the hash of the sources it was built from, so
// tests/test_room.py in the repo root notices a stale copy.
// Usage: npm run release   (builds first)
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const room = path.join(here, '..');
const out = path.join(room, '../content/room');

/** Same recipe as source_hash() in tests/test_room.py: sorted posix paths, no dotfiles, LF line endings. */
export function sourceHash() {
  const files = ['index.html', 'package.json', 'package-lock.json', 'tsconfig.json', 'vite.config.ts'];
  const walk = dir => {
    for (const name of fs.readdirSync(path.join(room, dir))) {
      if (name.startsWith('.')) continue; // .DS_Store and friends aren't in git
      const rel = dir + '/' + name;
      if (fs.statSync(path.join(room, rel)).isDirectory()) walk(rel); else files.push(rel);
    }
  };
  walk('src');
  const h = crypto.createHash('sha256');
  for (const rel of files.sort()) {
    h.update(rel + '\n');
    h.update(Buffer.from(fs.readFileSync(path.join(room, rel)).toString('binary').replace(/\r\n/g, '\n'), 'binary'));
    h.update('\n');
  }
  return h.digest('hex');
}

fs.mkdirSync(out, {recursive: true});
fs.copyFileSync(path.join(room, 'dist/index.html'), path.join(out, 'index.html'));
fs.writeFileSync(path.join(out, 'SOURCE_HASH'), sourceHash() + '\n');
console.log('已更新 content/room/index.html');

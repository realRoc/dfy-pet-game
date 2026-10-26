#!/usr/bin/env node
// Turns the generated pose sheets into small pixel atlases for the game.
// Usage: node tools/import-sprites.mjs <whale-tail/assets dir>
// Each pose is box-filtered so the idle pose has a fixed height, alpha is made
// binary and every frame shares one quantized palette, which keeps the
// generated art reading as a single pixel sprite.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {PNG} from 'pngjs';

const src = process.argv[2];
if (!src) { console.error('用法: node tools/import-sprites.mjs <demos/whale-tail/assets 目录>'); process.exit(1); }
const out = path.join(path.dirname(fileURLToPath(import.meta.url)), '../src/assets');

const read = f => PNG.sync.read(fs.readFileSync(path.join(src, f)));
const grid = (cols, rows) => Array.from({length: cols * rows}, (_, i) => [(i % cols) / cols, Math.floor(i / cols) / rows, 1 / cols, 1 / rows]);
// The casting hand in the sixth ultimate cell reaches into its neighbour's gutter.
const ultRegions = [[0, 0, .25, .5], [.25, 0, .25, .5], [.5, 0, .25, .5], [.75, 0, .25, .5], [0, .5, .25, .5], [.25, .5, .285, .5], [.535, .5, .215, .5], [.75, .5, .25, .5]];
const TAIL = ['idle', 'sink', 'coil', 'charged', 'twist', 'smear', 'strike', 'bend', 'sweep', 'rebound', 'hips', 'settle'];
const ULT = ['stand', 'chin', 'ponder', 'eureka', 'brace', 'release', 'recover', 'smug'];

function cutCells(img, regions) {
  return regions.map(([rx, ry, rw, rh]) => {
    const x0 = Math.round(rx * img.width), y0 = Math.round(ry * img.height);
    const w = Math.round(rw * img.width), h = Math.round(rh * img.height);
    let top = h, bottom = -1, left = w, right = -1;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      if (img.data[((y0 + y) * img.width + x0 + x) * 4 + 3] >= 128) { top = Math.min(top, y); bottom = Math.max(bottom, y); left = Math.min(left, x); right = Math.max(right, x); }
    }
    return {img, x0, y0, w, h, top, bottom, left, right};
  });
}

// Area-average each destination pixel; a pixel is opaque when most of its
// source area is, and then takes the mean colour of the opaque part only.
function downsample(cell, scale) {
  const w = Math.ceil(cell.w * scale), h = Math.ceil(cell.h * scale), px = new Float32Array(w * h * 4);
  const {img, x0, y0} = cell, inv = 1 / scale;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const sx0 = Math.floor(x * inv), sx1 = Math.min(cell.w, Math.floor((x + 1) * inv));
    const sy0 = Math.floor(y * inv), sy1 = Math.min(cell.h, Math.floor((y + 1) * inv));
    let n = 0, on = 0, r = 0, g = 0, b = 0;
    for (let sy = sy0; sy < sy1; sy++) for (let sx = sx0; sx < sx1; sx++) {
      const i = ((y0 + sy) * img.width + x0 + sx) * 4; n++;
      if (img.data[i + 3] >= 128) { on++; r += img.data[i]; g += img.data[i + 1]; b += img.data[i + 2]; }
    }
    const o = (y * w + x) * 4;
    if (n && on / n >= .5) { px[o] = r / on; px[o + 1] = g / on; px[o + 2] = b / on; px[o + 3] = 255; }
  }
  return {w, h, px};
}

function crop(frame) {
  let top = frame.h, bottom = -1, left = frame.w, right = -1;
  for (let y = 0; y < frame.h; y++) for (let x = 0; x < frame.w; x++) if (frame.px[(y * frame.w + x) * 4 + 3]) {
    top = Math.min(top, y); bottom = Math.max(bottom, y); left = Math.min(left, x); right = Math.max(right, x);
  }
  const w = right - left + 1, h = bottom - top + 1, px = new Float32Array(w * h * 4);
  for (let y = 0; y < h; y++) px.set(frame.px.subarray(((top + y) * frame.w + left) * 4, ((top + y) * frame.w + left + w) * 4), y * w * 4);
  // Foot anchor: centre of the opaque span across the lowest three rows.
  let fl = w, fr = 0;
  for (let y = Math.max(0, h - 3); y < h; y++) for (let x = 0; x < w; x++) if (px[(y * w + x) * 4 + 3]) { fl = Math.min(fl, x); fr = Math.max(fr, x); }
  return {w, h, px, ax: Math.round((fl + fr) / 2), ay: h - 1};
}

// k-means over every opaque pixel of a bank so all frames share one palette.
function quantize(frames, k) {
  const pts = [];
  for (const f of frames) for (let i = 0; i < f.px.length; i += 4) if (f.px[i + 3]) pts.push([f.px[i], f.px[i + 1], f.px[i + 2]]);
  pts.sort((a, b) => (a[0] * .3 + a[1] * .59 + a[2] * .11) - (b[0] * .3 + b[1] * .59 + b[2] * .11));
  let centers = Array.from({length: k}, (_, i) => [...pts[Math.floor((i + .5) / k * pts.length)]]);
  const nearest = p => { let best = 0, d = Infinity; centers.forEach((c, j) => { const e = (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2; if (e < d) { d = e; best = j; } }); return best; };
  for (let iter = 0; iter < 12; iter++) {
    const sum = centers.map(() => [0, 0, 0, 0]);
    for (const p of pts) { const s = sum[nearest(p)]; s[0] += p[0]; s[1] += p[1]; s[2] += p[2]; s[3]++; }
    centers = centers.map((c, j) => sum[j][3] ? [sum[j][0] / sum[j][3], sum[j][1] / sum[j][3], sum[j][2] / sum[j][3]] : c);
  }
  centers = centers.map(c => c.map(Math.round));
  for (const f of frames) for (let i = 0; i < f.px.length; i += 4) if (f.px[i + 3]) {
    const c = centers[nearest([f.px[i], f.px[i + 1], f.px[i + 2]])]; f.px[i] = c[0]; f.px[i + 1] = c[1]; f.px[i + 2] = c[2];
  }
}

function writeAtlas(name, frames, names) {
  const pad = 1, w = frames.reduce((s, f) => s + f.w + pad, 0), h = Math.max(...frames.map(f => f.h));
  const png = new PNG({width: w, height: h}), meta = {};
  let cx = 0;
  frames.forEach((f, n) => {
    for (let y = 0; y < f.h; y++) for (let x = 0; x < f.w; x++) {
      const s = (y * f.w + x) * 4, d = (y * w + cx + x) * 4;
      for (let c = 0; c < 4; c++) png.data[d + c] = f.px[s + c];
    }
    meta[names[n]] = {x: cx, y: 0, w: f.w, h: f.h, ax: f.ax, ay: f.ay};
    cx += f.w + pad;
  });
  fs.writeFileSync(path.join(out, name + '.png'), PNG.sync.write(png));
  fs.writeFileSync(path.join(out, name + '.json'), JSON.stringify(meta, null, 1) + '\n');
  console.log(`${name}: ${w}×${h}, ${frames.length} 帧`);
}

function bank(cells, idleHeight, idleIndex) {
  const idle = cells[idleIndex], scale = idleHeight / (idle.bottom - idle.top + 1);
  return cells.map(c => crop(downsample(c, scale)));
}

const tail = cutCells(read('tail-poses-v3.png'), grid(4, 3));
const ult = cutCells(read('ultimate-character.png'), ultRegions);
// Battle size: the idle pose is 72 px tall. Both sheets are normalised on their
// own idle pose so mixing tail and casting poses keeps the body the same size.
const battle = [...bank(tail, 72, 0), ...bank(ult, 72, 0)];
quantize(battle, 40);
writeAtlas('hero', battle, [...TAIL, ...ULT.map(n => 'ult-' + n)]);
// Close-up size for the ultimate cut-in, matching the original study's scale.
const closeUp = bank(ult, 100, 0);
quantize(closeUp, 48);
writeAtlas('hero-closeup', closeUp, ULT);
fs.copyFileSync(path.join(src, 'ultimate-whale-logo.png'), path.join(out, 'whale.png'));

// 后宅: an isometric room the player furnishes. The pet owns the data
// (room.py); this page draws it, edits it and sends the whole layout back after
// every change. Furniture is free: there is no currency.
import {Application, Assets, Container, Graphics, Sprite, Texture} from 'pixi.js';
import './style.css';
import {api} from './api';
import {
  cellsOf, depthOf, footprint, hex, itemPolys, newId, placementError, pointInPoly, project, shade, slotsOf, unproject,
} from './model';
import type {Catalog, Item, Layout, Placed, SetState, State} from './model';
import {Resident} from './resident';
import {saveQueue} from './saver';
import type {Spot} from './resident';
import {Ui} from './ui';

const WALL_H = 3.2;
const PANEL_W = 280;

type Mode = {kind: 'none'} | {kind: 'place'; item: string; rot: number; moving?: Placed} | {kind: 'selected'; id: string};
/** One piece on screen: what to add to the scene, whether a world point hits it, and its top centre. */
interface ItemView { view: Container; hit(wx: number, wy: number): boolean; top: [number, number] }

async function boot() {
  const app = new Application();
  await app.init({resizeTo: window, background: 0x2b3240, antialias: true, autoDensity: true, resolution: devicePixelRatio});
  document.getElementById('stage')!.appendChild(app.canvas);

  let cat: Catalog, state: State;
  try {
    [cat, state] = await Promise.all([api.catalog(), api.state()]);
  } catch (e) {
    document.body.insertAdjacentHTML('beforeend',
      `<div class="fatal">连不上桌宠：${(e as Error).message}<br>后宅要从桌宠的「🏠 后宅」打开。</div>`);
    return;
  }
  const byId = new Map(cat.items.map(it => [it.id, it]));
  const ch = state.character;
  document.title = `${ch.name}的后宅`;
  const tex = Object.fromEntries(await Promise.all((['front', 'side', 'back'] as const).map(
    async v => [v, await Assets.load<Texture>({src: ch.sprites[v], parser: 'texture'})]))) as Record<'front' | 'side' | 'back', Texture>;

  // Painted furniture, with its alpha so a click hits what you see. A picture that won't load falls back to boxes.
  const pics = new Map<string, {tex: Texture; alpha: Uint8Array}>();
  await Promise.all(cat.items.filter(it => it.sprite).map(async it => {
    try {
      const tex = await Assets.load<Texture>({src: it.sprite!.src, parser: 'texture'});
      pics.set(it.id, {tex, alpha: alphaOf(tex)});
    } catch (e) {
      console.warn(`家具图读不了，先画方块：${it.id}`, e);
    }
  }));

  let layout: Layout = state.layout;
  let sets: SetState[] = state.sets;
  let mode: Mode = {kind: 'none'};
  let hover: [number, number] | null = null;

  // ---------- scene ----------
  const world = new Container();
  const room = new Graphics();
  const rugs = new Container();
  const shadows = new Graphics();
  const things = new Container();
  things.sortableChildren = true;
  const overlay = new Graphics();
  const ghostLayer = new Container();
  world.addChild(room, rugs, shadows, things, overlay, ghostLayer);
  app.stage.addChild(world);
  const resident = new Resident(tex, ch, cat.room.w / 2, cat.room.d / 2);
  const itemViews = new Map<string, ItemView>();

  function fit() {
    const [lx] = project(0, cat.room.d), [rx] = project(cat.room.w, 0);
    const [, top] = project(0, 0, WALL_H), [, bottom] = project(cat.room.w, cat.room.d);
    const availW = app.screen.width - PANEL_W - 40, availH = app.screen.height - 60;
    const s = Math.min(availW / (rx - lx), availH / (bottom - top), 2.2);
    world.scale.set(s);
    world.position.set(PANEL_W + 20 + (availW - (rx - lx) * s) / 2 - lx * s, 30 + (availH - (bottom - top) * s) / 2 - top * s);
  }

  function drawRoom() {
    const wp = cat.wallpapers.find(w => w.id === layout.wallpaper)!, fl = cat.floors.find(f => f.id === layout.floor)!;
    const {w, d} = cat.room;
    const P = (x: number, y: number, z = 0) => project(x, y, z);
    room.clear();
    const wc = hex(wp.color), trim = hex(wp.trim ?? wp.color);
    room.poly([...P(0, 0), ...P(w, 0), ...P(w, 0, WALL_H), ...P(0, 0, WALL_H)]).fill(shade(wc, 0.94));
    room.poly([...P(0, 0), ...P(0, d), ...P(0, d, WALL_H), ...P(0, 0, WALL_H)]).fill(shade(wc, 0.82));
    room.poly([...P(0, 0), ...P(w, 0), ...P(w, 0, 0.25), ...P(0, 0, 0.25)]).fill(trim);
    room.poly([...P(0, 0), ...P(0, d), ...P(0, d, 0.25), ...P(0, 0, 0.25)]).fill(shade(trim, 0.88));
    for (let x = 0; x < w; x++) for (let y = 0; y < d; y++) {
      room.poly([...P(x, y), ...P(x + 1, y), ...P(x + 1, y + 1), ...P(x, y + 1)]).fill(hex((x + y) % 2 ? fl.alt ?? fl.color : fl.color));
    }
    room.poly([...P(0, 0), ...P(w, 0), ...P(w, d), ...P(0, d)]).stroke({width: 2, color: 0x000000, alpha: 0.15});
  }

  function itemView(item: Item, p: {x: number; y: number; rot: number}, alpha = 1, tint?: number): ItemView {
    const pic = pics.get(item.id);
    if (!pic) {
      const g = new Graphics();
      const polys = itemPolys(item, p);
      for (const poly of polys) {
        g.poly(poly.points).fill({color: tint === undefined ? poly.color : mix(poly.color, tint), alpha});
        g.poly(poly.points).stroke({width: 1, color: 0x000000, alpha: 0.12 * alpha});
      }
      const xs = polys.flatMap(q => q.points.filter((_, i) => i % 2 === 0)), ys = polys.flatMap(q => q.points.filter((_, i) => i % 2));
      return {view: g, hit: (wx, wy) => polys.some(q => pointInPoly(wx, wy, q.points)), top: [(Math.min(...xs) + Math.max(...xs)) / 2, Math.min(...ys)]};
    }
    // The picture's anchor goes on the footprint's back corner; facing the other way mirrors it about that point.
    const {anchor: [ax, ay], scale} = item.sprite!;
    const {width: w, height: h} = pic.tex;
    const [ox, oy] = project(p.x, p.y), flip = p.rot % 2 ? -1 : 1;
    const s = new Sprite(pic.tex);
    s.anchor.set(ax / w, ay / h);
    s.position.set(ox, oy);
    s.scale.set(flip / scale, 1 / scale);
    s.alpha = alpha;
    if (tint !== undefined) s.tint = tint;
    return {
      view: s,
      hit: (wx, wy) => {
        const px = Math.floor(ax + (wx - ox) * scale * flip), py = Math.floor(ay + (wy - oy) * scale);
        return px >= 0 && py >= 0 && px < w && py < h && pic.alpha[py * w + px] > 40;
      },
      top: [ox + (w / 2 - ax) * flip / scale, oy - ay / scale],
    };
  }

  /** A soft patch of shade under a standing piece, so it sits on the floor. */
  function drawShadow(item: Item, p: {x: number; y: number; rot: number}) {
    const [fw, fd] = footprint(item, p.rot), m = 0.08;
    const x0 = p.x + m, y0 = p.y + m, x1 = p.x + fw - m, y1 = p.y + fd - m;
    shadows.poly([...project(x0, y0), ...project(x1, y0), ...project(x1, y1), ...project(x0, y1)]).fill({color: 0x2b1d14, alpha: 0.13});
  }

  function drawFurniture() {
    for (const v of itemViews.values()) v.view.destroy();
    itemViews.clear();
    shadows.clear();
    const selected = mode.kind === 'selected' ? mode.id : mode.kind === 'place' ? mode.moving?.id : undefined;
    for (const p of layout.placed) {
      const item = byId.get(p.item)!;
      if (mode.kind === 'place' && mode.moving?.id === p.id) continue;   // picked up: drawn as the ghost
      const v = itemView(item, p, 1, p.id === selected ? 0xfff2a8 : undefined);
      v.view.zIndex = depthOf(item, p) * 10;
      (item.layer === 'rug' ? rugs : things).addChild(v.view);
      if (item.layer === 'object') drawShadow(item, p);
      itemViews.set(p.id, v);
    }
    if (!resident.view.parent) things.addChild(resident.view);
  }

  function ghost(): Placed | null {
    if (mode.kind !== 'place' || !hover) return null;
    const item = byId.get(mode.item)!;
    const [fw, fd] = footprint(item, mode.rot);
    return {id: mode.moving?.id ?? '', item: mode.item, x: hover[0] - Math.floor((fw - 1) / 2), y: hover[1] - Math.floor((fd - 1) / 2), rot: mode.rot};
  }

  function drawOverlay() {
    overlay.clear();
    for (const c of ghostLayer.removeChildren()) c.destroy();
    const g = ghost();
    if (g) {
      const item = byId.get(g.item)!;
      const err = placementError(cat, byId, layout.placed, g, mode.kind === 'place' ? mode.moving?.id : undefined);
      for (const [cx, cy] of cellsOf(item, g)) {
        if (cx < 0 || cy < 0 || cx >= cat.room.w || cy >= cat.room.d) continue;
        overlay.poly([...project(cx, cy), ...project(cx + 1, cy), ...project(cx + 1, cy + 1), ...project(cx, cy + 1)])
          .fill({color: err ? 0xff5a5a : 0x5ad17a, alpha: 0.45});
      }
      ghostLayer.addChild(itemView(item, g, 0.7, err ? 0xff8080 : undefined).view);
      ui.hint(err ? `放不下：${err}` : '左键放下 · R 旋转 · 右键 / Esc 取消');
    }
  }

  // ---------- resident ----------
  function spots(): Spot[] {
    const out: Spot[] = [];
    for (const p of layout.placed) {
      if (mode.kind === 'place' && mode.moving?.id === p.id) continue;
      const item = byId.get(p.item)!;
      slotsOf(item, p, cat.room).forEach((s, i) =>
        out.push({key: `${p.id}#${i}`, pose: s.pose, x: s.x, y: s.y, z: s.z, label: `在${item.name}${cat.poses[s.pose]?.label ?? ''}`}));
    }
    return out;
  }

  function freeCell(): [number, number] | null {
    const taken = new Set<string>();
    for (const p of layout.placed) {
      const item = byId.get(p.item)!;
      if (item.layer === 'object') for (const [cx, cy] of cellsOf(item, p)) taken.add(`${cx},${cy}`);
    }
    const free: [number, number][] = [];
    for (let x = 0; x < cat.room.w; x++) for (let y = 0; y < cat.room.d; y++) if (!taken.has(`${x},${y}`)) free.push([x + 0.5, y + 0.5]);
    return free.length ? free[Math.floor(Math.random() * free.length)] : null;
  }

  // ---------- editing ----------
  const queueSave = saveQueue({
    get: () => layout,
    set: (next: Layout) => { layout = next; },
    put: api.putLayout,
    saved: r => {
      const before = sets;
      sets = r.sets;
      const news: string[] = [];
      for (const s of sets) {
        if (s.complete && !before.find(x => x.id === s.id)?.complete) {
          news.push(`集齐「${s.name}」！`);
          resident.say(`集齐${s.name}啦！`);
        }
      }
      if (news.length) ui.toast(news.join('　'));
      redraw();
    },
    failed: e => {
      ui.toast(`没存上：${e.message}`, true);
      redraw();
    },
  });
  function commit(next: Layout) {
    void queueSave(next);
    redraw();
  }

  function setMode(m: Mode) {
    mode = m;
    redraw();
    ui.hint(mode.kind === 'selected' ? 'R 旋转 · Delete 收起 · Esc 取消选择'
      : mode.kind === 'place' ? '左键放下 · R 旋转 · 右键 / Esc 取消' : '点左边的家具摆进房间，点房间里的家具可以移动、旋转、收起');
  }

  function placeAtHover() {
    const g = ghost();
    if (!g || mode.kind !== 'place') return;
    if (placementError(cat, byId, layout.placed, g, mode.moving?.id)) return;
    const placed: Placed = {...g, id: mode.moving?.id ?? newId(g.item)};
    const rest = layout.placed.filter(p => p.id !== placed.id);
    setMode({kind: 'none'});
    void commit({...layout, placed: [...rest, placed]});
  }

  function rotate() {
    if (mode.kind === 'place') { mode = {...mode, rot: (mode.rot + 1) % 2}; redraw(); return; }
    if (mode.kind !== 'selected') return;
    const id = mode.id;
    const p = layout.placed.find(x => x.id === id);
    if (!p) return;
    const turned = {...p, rot: (p.rot + 1) % 2};
    const err = placementError(cat, byId, layout.placed, turned, p.id);
    if (err) { ui.toast(`转不过来：${err}`, true); return; }
    void commit({...layout, placed: layout.placed.map(x => x.id === p.id ? turned : x)});
  }

  function stash() {
    if (mode.kind !== 'selected') return;
    const id = mode.id;
    setMode({kind: 'none'});
    void commit({...layout, placed: layout.placed.filter(p => p.id !== id)});
  }

  function pickUp() {
    if (mode.kind !== 'selected') return;
    const p = layout.placed.find(x => x.id === (mode as {id: string}).id);
    if (p) setMode({kind: 'place', item: p.item, rot: p.rot, moving: p});
  }

  function hitTest(wx: number, wy: number): string | null {
    const order = [...layout.placed].sort((a, b) => {
      const ia = byId.get(a.item)!, ib = byId.get(b.item)!;
      return (ib.layer === 'object' ? 1000 : 0) + depthOf(ib, b) - (ia.layer === 'object' ? 1000 : 0) - depthOf(ia, a);
    });
    for (const p of order) {
      const v = itemViews.get(p.id);
      if (v?.hit(wx, wy)) return p.id;
    }
    return null;
  }

  // ---------- ui ----------
  const ui = new Ui(cat, {
    pick: id => setMode({kind: 'place', item: id, rot: 0}),
    wallpaper: id => void commit({...layout, wallpaper: id}),
    floor: id => void commit({...layout, floor: id}),
    rotate, stash, move: pickUp,
  });

  function redraw() {
    drawRoom();
    drawFurniture();
    drawOverlay();
    resident.refresh(spots());
    ui.render(layout, sets, mode.kind === 'selected' ? mode.id : null);
    if (mode.kind === 'selected') {
      const v = itemViews.get(mode.id);
      if (v) {
        const top = world.toGlobal({x: v.top[0], y: v.top[1]});
        ui.showToolbar(top.x, top.y);
      }
    } else ui.hideToolbar();
  }

  // ---------- input ----------
  app.stage.eventMode = 'static';
  app.stage.hitArea = app.screen;
  app.stage.on('pointermove', e => {
    const local = world.toLocal(e.global);
    const [gx, gy] = unproject(local.x, local.y);
    const cell: [number, number] = [Math.floor(gx), Math.floor(gy)];
    if (mode.kind === 'place' && (!hover || hover[0] !== cell[0] || hover[1] !== cell[1])) { hover = cell; drawOverlay(); }
    else hover = cell;
  });
  app.stage.on('pointerdown', e => {
    if (e.button === 2) { setMode({kind: 'none'}); return; }
    if (e.button !== 0) return;
    if (mode.kind === 'place') { placeAtHover(); return; }
    const local = world.toLocal(e.global);
    const id = hitTest(local.x, local.y);
    setMode(id ? {kind: 'selected', id} : {kind: 'none'});
  });
  app.canvas.addEventListener('contextmenu', e => e.preventDefault());
  window.addEventListener('keydown', e => {
    if (e.key === 'Escape') setMode({kind: 'none'});
    else if (e.key === 'r' || e.key === 'R') rotate();
    else if (e.key === 'Delete' || e.key === 'Backspace') stash();
  });
  window.addEventListener('resize', () => { fit(); redraw(); });

  app.ticker.add(t => {
    resident.update(t.deltaMS / 1000, mode.kind === 'place' ? [] : spots(), freeCell);
    resident.view.zIndex = (resident.x + resident.y) * 10 + 5;
  });

  fit();
  setMode({kind: 'none'});
  resident.say(layout.placed.length ? '欢迎回来～' : '空荡荡的……摆点家具吧！', 3.5);
}

/** The alpha channel of a loaded picture, one byte per pixel, for hit testing. */
function alphaOf(tex: Texture): Uint8Array {
  const {width: w, height: h} = tex;
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  const g = c.getContext('2d', {willReadFrequently: true})!;
  g.drawImage(tex.source.resource as CanvasImageSource, 0, 0, w, h);
  const rgba = g.getImageData(0, 0, w, h).data, out = new Uint8Array(w * h);
  for (let i = 0; i < out.length; i++) out[i] = rgba[i * 4 + 3];
  return out;
}

function mix(a: number, b: number): number {
  const c = (s: number) => [(s >> 16) & 255, (s >> 8) & 255, s & 255];
  const [r1, g1, b1] = c(a), [r2, g2, b2] = c(b);
  return (Math.round((r1 + r2) / 2) << 16) | (Math.round((g1 + g2) / 2) << 8) | Math.round((b1 + b2) / 2);
}

void boot();

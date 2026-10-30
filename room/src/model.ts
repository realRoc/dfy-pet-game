// Data shapes shared with the pet's RoomAPI (room.py), and the pure geometry
// and placement rules. No DOM, no Pixi: tests/model.test.ts covers this file.

export type Vec3 = [number, number, number];

export interface Box { at: Vec3; size: Vec3; color: string }
export interface Slot { pose: string; at: [number, number]; z?: number }
export interface Item {
  id: string; name: string; set?: string; size: [number, number];
  layer: 'object' | 'rug'; boxes: Box[]; slots?: Slot[];
}
export interface Surface { id: string; name: string; color: string; trim?: string; alt?: string }
export interface Catalog {
  room: {w: number; d: number};
  poses: Record<string, {label: string}>;
  wallpapers: Surface[];
  floors: Surface[];
  sets: {id: string; name: string}[];
  items: Item[];
}
export interface Placed { id: string; item: string; x: number; y: number; rot: number }
export interface Layout { version?: number; wallpaper: string; floor: string; placed: Placed[] }
export interface SetState { id: string; name: string; have: number; total: number; complete: boolean; missing: string[] }
export interface CharacterInfo { id: string; name: string; side_faces: 'left' | 'right'; sprites: {front: string; side: string; back: string} }
export interface State { layout: Layout; sets: SetState[]; character: CharacterInfo }

// ---------- isometric projection ----------
// Grid x runs to the lower right, grid y to the lower left, z up. (0, 0, 0) is the back corner of the floor.
export const TILE_W = 64;
export const TILE_H = 32;
export const UNIT_Z = 36;   // one cell of height on screen, about one cell edge

export function project(x: number, y: number, z = 0): [number, number] {
  return [(x - y) * TILE_W / 2, (x + y) * TILE_H / 2 - z * UNIT_Z];
}

/** Screen point back to the floor (z = 0). */
export function unproject(sx: number, sy: number): [number, number] {
  const a = sx / (TILE_W / 2), b = sy / (TILE_H / 2);
  return [(a + b) / 2, (b - a) / 2];
}

// ---------- rotation ----------
// rot counts quarter turns clockwise (seen from above). Item data is authored at rot 0.

export function footprint(item: Item, rot: number): [number, number] {
  const [w, d] = item.size;
  return rot % 2 ? [d, w] : [w, d];
}

/** A box inside the footprint after `rot` quarter turns. */
export function rotateBox(box: Box, size: [number, number], rot: number): Box {
  let [x, y, z] = box.at, [w, d, h] = box.size, [fw, fd] = size;
  for (let i = 0; i < ((rot % 4) + 4) % 4; i++) {
    [x, y, w, d] = [fd - y - d, x, d, w];
    [fw, fd] = [fd, fw];
  }
  return {at: [x, y, z], size: [w, d, h], color: box.color};
}

/** A point inside (or next to) the footprint after `rot` quarter turns. */
export function rotatePoint(p: [number, number], size: [number, number], rot: number): [number, number] {
  let [x, y] = p, [fw, fd] = size;
  for (let i = 0; i < ((rot % 4) + 4) % 4; i++) {
    [x, y] = [fd - y, x];
    [fw, fd] = [fd, fw];
  }
  return [x, y];
}

// ---------- placement rules (mirror validate_layout in room.py, which has the final say) ----------

export function cellsOf(item: Item, p: {x: number; y: number; rot: number}): [number, number][] {
  const [fw, fd] = footprint(item, p.rot);
  const out: [number, number][] = [];
  for (let cx = p.x; cx < p.x + fw; cx++) for (let cy = p.y; cy < p.y + fd; cy++) out.push([cx, cy]);
  return out;
}

/** Why `candidate` can't go here, or null if it can. `ignore` is the instance being moved. */
export function placementError(cat: Catalog, byId: Map<string, Item>, placed: Placed[], candidate: Placed, ignore?: string): string | null {
  const item = byId.get(candidate.item);
  if (!item) return '没有这件家具';
  const [fw, fd] = footprint(item, candidate.rot);
  if (candidate.x < 0 || candidate.y < 0 || candidate.x + fw > cat.room.w || candidate.y + fd > cat.room.d) return '出界了';
  const taken = new Map<string, string>();
  for (const p of placed) {
    if (p.id === ignore || p.id === candidate.id) continue;
    const other = byId.get(p.item);
    if (!other || other.layer !== item.layer) continue;
    for (const [cx, cy] of cellsOf(other, p)) taken.set(`${cx},${cy}`, other.name);
  }
  for (const [cx, cy] of cellsOf(item, candidate)) {
    const hit = taken.get(`${cx},${cy}`);
    if (hit) return `和${hit}叠在一起了`;
  }
  return null;
}

// ---------- drawing data ----------

export interface Poly { points: number[]; color: number }

export function hex(color: string): number {
  return parseInt(color.replace('#', ''), 16);
}

export function shade(color: number, k: number): number {
  const r = Math.min(255, Math.round(((color >> 16) & 255) * k));
  const g = Math.min(255, Math.round(((color >> 8) & 255) * k));
  const b = Math.min(255, Math.round((color & 255) * k));
  return (r << 16) | (g << 8) | b;
}

/** Screen polygons for one placed item, back to front: per box its +y face, +x face, then top. */
export function itemPolys(item: Item, p: {x: number; y: number; rot: number}): Poly[] {
  const boxes = item.boxes.map(b => rotateBox(b, item.size, p.rot));
  boxes.sort((a, b) => (a.at[0] + a.size[0] / 2 + a.at[1] + a.size[1] / 2) - (b.at[0] + b.size[0] / 2 + b.at[1] + b.size[1] / 2)
    || a.at[2] - b.at[2]);
  const out: Poly[] = [];
  for (const b of boxes) {
    const [bx, by, bz] = b.at, [w, d, h] = b.size;
    const x0 = p.x + bx, y0 = p.y + by, x1 = x0 + w, y1 = y0 + d, z1 = bz + h;
    const pt = (x: number, y: number, z: number) => project(x, y, z);
    const c = hex(b.color);
    out.push({points: [...pt(x0, y1, bz), ...pt(x1, y1, bz), ...pt(x1, y1, z1), ...pt(x0, y1, z1)], color: shade(c, 0.72)});
    out.push({points: [...pt(x1, y0, bz), ...pt(x1, y1, bz), ...pt(x1, y1, z1), ...pt(x1, y0, z1)], color: shade(c, 0.86)});
    out.push({points: [...pt(x0, y0, z1), ...pt(x1, y0, z1), ...pt(x1, y1, z1), ...pt(x0, y1, z1)], color: c});
  }
  return out;
}

/** Painter's order key for things standing on the floor: further back draws first. */
export function depthOf(item: Item, p: {x: number; y: number; rot: number}): number {
  const [fw, fd] = footprint(item, p.rot);
  return p.x + fw / 2 + p.y + fd / 2;
}

export function pointInPoly(px: number, py: number, pts: number[]): boolean {
  let inside = false;
  for (let i = 0, j = pts.length - 2; i < pts.length; j = i, i += 2) {
    const xi = pts[i], yi = pts[i + 1], xj = pts[j], yj = pts[j + 1];
    if ((yi > py) !== (yj > py) && px < (xj - xi) * (py - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Where the character stands for each slot of a placed item, in grid coordinates. */
export function slotsOf(item: Item, p: Placed, room: {w: number; d: number}): {pose: string; x: number; y: number; z: number}[] {
  return (item.slots ?? []).map(s => {
    const [sx, sy] = rotatePoint(s.at, item.size, p.rot);
    return {
      pose: s.pose,
      x: Math.min(room.w - 0.3, Math.max(0.3, p.x + sx)),
      y: Math.min(room.d - 0.3, Math.max(0.3, p.y + sy)),
      z: s.z ?? defaultSlotZ(item, s),
    };
  });
}

/** Lying on furniture: on top of whatever is under the slot. Standing next to it: the floor. */
function defaultSlotZ(item: Item, s: Slot): number {
  if (s.pose !== 'lie' && s.pose !== 'sleep') return 0;
  const [ax, ay] = s.at;
  let top = 0;
  for (const b of item.boxes) {
    if (ax >= b.at[0] && ax <= b.at[0] + b.size[0] && ay >= b.at[1] && ay <= b.at[1] + b.size[1] && b.size[2] < 0.5) {
      top = Math.max(top, b.at[2] + b.size[2]);
    }
  }
  return top;
}

export function newId(itemId: string): string {
  return `${itemId}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`.slice(0, 40);
}

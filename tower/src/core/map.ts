import {Rng} from './rng';

export type RoomType = 'monster' | 'elite' | 'event' | 'shop' | 'rest' | 'chest' | 'bug' | 'boss';

export const FLOORS = 15;
export const COLS = 7;
export const PATHS = 6;
/** 0-based floors with a fixed room: floor 1 fights, floor 9 a chest, floor 15 a nap before the boss. */
export const FIXED: Partial<Record<number, RoomType>> = {0: 'monster', 8: 'chest', 14: 'rest'};
export const WEIGHTS: [RoomType, number][] = [['monster', 45], ['event', 22], ['rest', 12], ['elite', 10], ['shop', 6], ['bug', 5]];
export const MAX_BUGS = 2;
/** Rooms that shouldn't follow themselves on a path or appear twice among one node's children. */
const SPECIAL: RoomType[] = ['elite', 'rest', 'shop', 'bug'];

export interface MapNode {
  floor: number;
  col: number;
  type: RoomType;
  /** Columns this node connects to on the next floor. The last floor leads to the boss. */
  next: number[];
}

export interface GameMap {
  seed: number;
  /** floors[f][col] is null where no path passes. */
  floors: (MapNode | null)[][];
}

/** Why a room type can't go on a floor, by the floor rules alone. */
export function floorAllows(type: RoomType, floor: number, bugsSoFar: number): boolean {
  if (FIXED[floor]) return FIXED[floor] === type;
  if ((type === 'elite' || type === 'rest') && floor < 5) return false;
  if (type === 'rest' && floor === 13) return false;
  if (type === 'bug' && (floor < 3 || bugsSoFar >= MAX_BUGS)) return false;
  return type !== 'boss';
}

/**
 * Slay the Spire's layout: six paths climb from the bottom, each step moving
 * at most one column sideways and never crossing an edge already drawn.
 * Rooms are then rolled floor by floor with the floor rules above.
 */
export function generateMap(seed: number): GameMap {
  const rng = new Rng(seed);
  const edges: Set<number>[][] = Array.from({length: FLOORS}, () => Array.from({length: COLS}, () => new Set<number>()));
  let firstStart = -1;
  for (let path = 0; path < PATHS; path++) {
    let col = rng.int(0, COLS - 1);
    // The first two paths start apart so there are always at least two ways up.
    if (path === 0) firstStart = col;
    while (path === 1 && col === firstStart) col = rng.int(0, COLS - 1);
    for (let f = 0; f < FLOORS - 1; f++) {
      const options = [col - 1, col, col + 1].filter(c => c >= 0 && c < COLS && !crosses(edges[f], col, c));
      const to = rng.pick(options);
      edges[f][col].add(to);
      col = to;
    }
    edges[FLOORS - 1][col].add(0); // everything on the top floor leads to the boss
  }

  const floors: (MapNode | null)[][] = edges.map((row, f) => row.map((next, col) =>
    next.size ? {floor: f, col, type: 'monster' as RoomType, next: [...next].sort((a, b) => a - b)} : null));
  const top = floors[FLOORS - 1];
  for (const n of top) if (n) n.next = [];

  let bugs = 0;
  for (let f = 0; f < FLOORS; f++) {
    for (const node of floors[f]) {
      if (!node) continue;
      const parents = f ? floors[f - 1].filter(p => p?.next.includes(node.col)) as MapNode[] : [];
      // Siblings already rolled: other children of the same parents.
      const siblings = parents.flatMap(p => p.next.filter(c => c < node.col).map(c => floors[f][c]!.type));
      const allowed = WEIGHTS.filter(([type]) => floorAllows(type, f, bugs)
        && !(SPECIAL.includes(type) && (parents.some(p => p.type === type) || siblings.includes(type))));
      node.type = FIXED[f] ?? roll(rng, allowed);
      if (node.type === 'bug') bugs++;
    }
  }
  return {seed, floors};
}

/** Would an edge from `from` to `to` cross an edge already leaving this floor? */
function crosses(row: Set<number>[], from: number, to: number): boolean {
  if (to === from + 1) return !!row[from + 1]?.has(from);
  if (to === from - 1) return !!row[from - 1]?.has(from);
  return false;
}

function roll(rng: Rng, options: [RoomType, number][]): RoomType {
  if (!options.length) return 'monster';
  let r = rng.next() * options.reduce((s, [, w]) => s + w, 0);
  for (const [type, w] of options) { r -= w; if (r < 0) return type; }
  return options[options.length - 1][0];
}

/** Nodes the player may step to: the bottom row before the climb starts. */
export function nextChoices(map: GameMap, at: {floor: number; col: number} | null): MapNode[] {
  if (!at) return map.floors[0].filter((n): n is MapNode => !!n);
  if (at.floor === FLOORS - 1) return [];
  const here = map.floors[at.floor][at.col]!;
  return here.next.map(c => map.floors[at.floor + 1][c]!);
}

/** All edges as [floor, fromCol, toCol], for drawing and tests. */
export function mapEdges(map: GameMap): [number, number, number][] {
  return map.floors.flatMap((row, f) => row.flatMap(n => (n ? n.next.map(c => [f, n.col, c] as [number, number, number]) : [])));
}

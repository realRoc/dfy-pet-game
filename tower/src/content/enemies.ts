import type {EnemyUnit, Intent} from '../core/types';
import type {Rng} from '../core/rng';

export interface EnemyDef {
  kind: string;
  name: string;
  hp: [number, number];
  moves: Record<string, {name: string; intent: Intent}>;
  /** Picks the next move. `turn` counts this enemy's own turns from 0. */
  next(e: EnemyUnit, rng: Rng, turn: number): string;
}

// Not three times in a row, the usual Slay the Spire rule for random enemies.
const fresh = (e: EnemyUnit, move: string) => !(e.history.at(-1) === move && e.history.at(-2) === move);

const defs: EnemyDef[] = [
  {kind: 'dummy', name: '训练木桩', hp: [32, 32],
    moves: {
      daze: {name: '发呆', intent: {kind: 'idle'}},
      bonk: {name: '回弹', intent: {kind: 'attack', dmg: 5, times: 1}},
      brace: {name: '扎稳', intent: {kind: 'attackDefend', dmg: 3, times: 1, block: 5}},
    },
    next: (_e, _r, turn) => (turn === 0 ? 'daze' : turn % 2 ? 'bonk' : 'brace')},
  {kind: 'crab', name: '钳钳蟹', hp: [20, 24],
    moves: {
      pinch: {name: '夹一下', intent: {kind: 'attack', dmg: 7, times: 1}},
      shell: {name: '缩壳', intent: {kind: 'attackDefend', dmg: 3, times: 1, block: 7}},
    },
    next: (e, rng) => { const m = rng.next() < .6 ? 'pinch' : 'shell'; return fresh(e, m) ? m : m === 'pinch' ? 'shell' : 'pinch'; }},
  {kind: 'gull', name: '抢饭海鸥', hp: [14, 17],
    moves: {
      peck: {name: '啄白饭', intent: {kind: 'attack', dmg: 2, times: 3}},
      snatch: {name: '叼走饭碗', intent: {kind: 'attackDebuff', dmg: 5, times: 1, status: 'weak', n: 1}},
    },
    next: (e, rng, turn) => (turn === 0 ? 'snatch' : fresh(e, 'peck') && rng.next() < .65 ? 'peck' : 'snatch')},
  {kind: 'jelly', name: '服务器繁忙水母', hp: [60, 64],
    moves: {
      busy: {name: '服务器繁忙', intent: {kind: 'stuff', id: 'busy', n: 2, block: 6}},
      zap: {name: '过载电击', intent: {kind: 'attack', dmg: 11, times: 1}},
      sting: {name: '请稍后再试', intent: {kind: 'attackDebuff', dmg: 6, times: 1, status: 'vulnerable', n: 2}},
    },
    next: (_e, _r, turn) => ['busy', 'zap', 'sting'][turn % 3]},
];

export const ENEMIES: Record<string, EnemyDef> = Object.fromEntries(defs.map(d => [d.kind, d]));

export interface Encounter { id: string; name: string; enemies: string[]; elite?: boolean }
export const GAUNTLET: Encounter[] = [
  {id: 'tutorial', name: '海边训练场', enemies: ['dummy']},
  {id: 'beach', name: '午饭时间的沙滩', enemies: ['crab', 'gull']},
  {id: 'elite', name: '精英 · 服务器繁忙', enemies: ['jelly'], elite: true},
];

import type {EnemyUnit, Intent} from '../core/types';
import type {Rng} from '../core/rng';

export interface EnemyDef {
  kind: string;
  name: string;
  /** Shown in the tooltip under the name, for names that are a joke on their own. */
  note?: string;
  hp: [number, number];
  moves: Record<string, {name: string; intent: Intent}>;
  /** Picks the next move. `turn` counts this enemy's own turns from 0. */
  next(e: EnemyUnit, rng: Rng, turn: number): string;
}

// Not three times in a row, the usual Slay the Spire rule for random enemies.
const fresh = (e: EnemyUnit, move: string) => !(e.history.at(-1) === move && e.history.at(-2) === move);
const either = (e: EnemyUnit, rng: Rng, a: string, b: string, pa: number) => {
  const m = rng.next() < pa ? a : b;
  return fresh(e, m) ? m : m === a ? b : a;
};

const defs: EnemyDef[] = [
  // ── 普通 ──
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
    next: (e, rng) => either(e, rng, 'pinch', 'shell', .6)},
  {kind: 'gull', name: '抢饭海鸥', hp: [14, 17],
    moves: {
      peck: {name: '啄白饭', intent: {kind: 'attack', dmg: 2, times: 3}},
      snatch: {name: '叼走饭碗', intent: {kind: 'attackDebuff', dmg: 5, times: 1, status: 'weak', n: 1}},
    },
    next: (e, rng, turn) => (turn === 0 ? 'snatch' : fresh(e, 'peck') && rng.next() < .65 ? 'peck' : 'snatch')},
  {kind: 'process', name: '野鸡进程', note: '「这是哪来的野鸡进程？」', hp: [18, 22],
    moves: {
      hog: {name: '占满 CPU', intent: {kind: 'buff', status: 'strength', n: 2}},
      grab: {name: '抢内存', intent: {kind: 'attack', dmg: 6, times: 1}},
      fork: {name: 'fork 炸弹', intent: {kind: 'attack', dmg: 3, times: 2}},
    },
    next: (e, rng, turn) => (turn % 3 === 0 ? 'hog' : either(e, rng, 'grab', 'fork', .5))},
  {kind: 'starfish', name: '幻觉海星', note: '说什么都很自信。', hp: [26, 30],
    moves: {
      cite: {name: '编造引用', intent: {kind: 'debuff', status: 'weak', n: 2}},
      sure: {name: '一本正经', intent: {kind: 'attack', dmg: 8, times: 1}},
      smug: {name: '自信满满', intent: {kind: 'attackDefend', dmg: 5, times: 1, block: 6}},
    },
    next: (e, rng, turn) => (turn === 0 ? 'cite' : e.history.at(-1) === 'cite' ? 'sure' : either(e, rng, 'smug', 'cite', .6))},

  // ── 精英 ──
  {kind: 'jelly', name: '服务器繁忙水母', hp: [60, 64],
    moves: {
      busy: {name: '服务器繁忙', intent: {kind: 'stuff', id: 'busy', n: 2, block: 6}},
      zap: {name: '过载电击', intent: {kind: 'attack', dmg: 11, times: 1}},
      sting: {name: '请稍后再试', intent: {kind: 'attackDebuff', dmg: 6, times: 1, status: 'vulnerable', n: 2}},
    },
    next: (_e, _r, turn) => ['busy', 'zap', 'sting'][turn % 3]},
  {kind: 'firewall', name: '权限不足防火墙', note: '想结束它的进程？权限不足。', hp: [68, 72],
    moves: {
      scan: {name: '全盘扫描', intent: {kind: 'attack', dmg: 4, times: 3}},
      isolate: {name: '拦截隔离', intent: {kind: 'stuff', id: 'quarantine', n: 2, block: 8}},
      deny: {name: '权限不足', intent: {kind: 'attackDebuff', dmg: 8, times: 1, status: 'vulnerable', n: 2}},
    },
    next: (_e, _r, turn) => ['isolate', 'scan', 'deny'][turn % 3]},
  {kind: 'turtle', name: '下周见老海龟', note: '每次都说下周见。', hp: [80, 86],
    moves: {
      shell: {name: '缩壳', intent: {kind: 'defend', block: 14}},
      soon: {name: '下周见……', intent: {kind: 'charge'}},
      launch: {name: '终于发布！', intent: {kind: 'attack', dmg: 26, times: 1}},
      bite: {name: '慢吞吞地咬', intent: {kind: 'attackDefend', dmg: 9, times: 1, block: 6}},
    },
    next: (_e, _r, turn) => ['shell', 'soon', 'launch', 'bite'][turn % 4]},

  // ── Bug 房 ──
  {kind: 'glitch', name: '涔辩爜铏�', note: '（乱码虫。UTF-8 被当成 GBK 读了。）', hp: [44, 48],
    moves: {
      kun: {name: '锟斤拷', intent: {kind: 'attack', dmg: 5, times: 2}},
      tang: {name: '烫烫烫', intent: {kind: 'attackDebuff', dmg: 7, times: 1, status: 'weak', n: 1}},
      segv: {name: 'Segmentation fault', intent: {kind: 'buff', status: 'strength', n: 2, block: 6}},
    },
    next: (_e, _r, turn) => ['kun', 'segv', 'tang'][turn % 3]},

  // ── 关底 Boss ──
  {kind: 'blackWhale', name: '黑鲸 · 更强的Agent', note: '「显然有一个更强的 Agent 在这。」', hp: [160, 160],
    moves: {
      takeover: {name: '接管工作目录', intent: {kind: 'stuff', id: 'quarantine', n: 2, block: 12}},
      kill: {name: '结束野鸡进程', intent: {kind: 'attack', dmg: 8, times: 2}},
      plan: {name: '调度子任务……', intent: {kind: 'charge'}},
      harness: {name: 'Harness 全开', intent: {kind: 'attack', dmg: 25, times: 1}},
      swarm: {name: '并行 Agent', intent: {kind: 'attack', dmg: 4, times: 4}},
      stronger: {name: '显然有一个更强的Agent在这', intent: {kind: 'buff', status: 'strength', n: 3, block: 15}},
    },
    next: (e, _r, turn) => {
      if (e.hp <= e.maxHp / 2 && !e.history.includes('stronger')) return 'stronger';
      return turn === 0 ? 'takeover' : ['kill', 'plan', 'harness', 'takeover', 'swarm'][(turn - 1) % 5];
    }},
];

export const ENEMIES: Record<string, EnemyDef> = Object.fromEntries(defs.map(d => [d.kind, d]));

export interface Encounter { id: string; name: string; enemies: string[]; elite?: boolean; boss?: boolean }

/** The first three fights of a run come from here. */
export const EASY: Encounter[] = [
  {id: 'tutorial', name: '海边训练场', enemies: ['dummy']},
  {id: 'crab', name: '钳钳蟹拦路', enemies: ['crab']},
  {id: 'gulls', name: '抢饭的海鸥', enemies: ['gull', 'gull']},
  {id: 'process', name: '野鸡进程', enemies: ['process']},
];
export const NORMAL: Encounter[] = [
  {id: 'beach', name: '午饭时间的沙滩', enemies: ['crab', 'gull']},
  {id: 'processes', name: '后台进程开太多', enemies: ['process', 'process']},
  {id: 'tidepool', name: '幻觉潮池', enemies: ['starfish', 'crab']},
  {id: 'flock', name: '海鸥带着海星', enemies: ['gull', 'starfish']},
  {id: 'busyBeach', name: '谁在抢我的饭', enemies: ['process', 'gull']},
];
export const ELITES: Encounter[] = [
  {id: 'jelly', name: '精英 · 服务器繁忙', enemies: ['jelly'], elite: true},
  {id: 'firewall', name: '精英 · 权限不足', enemies: ['firewall'], elite: true},
  {id: 'turtle', name: '精英 · 下周见', enemies: ['turtle'], elite: true},
];
export const BOSS: Encounter = {id: 'boss', name: '黑鲸 · 更强的Agent', enemies: ['blackWhale'], boss: true};
export const BUG_FIGHT: Encounter = {id: 'bug', name: 'Bug 房 · 涔辩爜铏�', enemies: ['glitch'], elite: true};
export const KILL_PROCESS: Encounter = {id: 'killProcess', name: '结束进程', enemies: ['process', 'process', 'process']};

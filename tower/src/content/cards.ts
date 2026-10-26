import type {CardDef} from '../core/types';

// Names lean on the 大肥鱼 community memes: 吃白饭, 铁盆, 已思考3秒,
// 上错模型了, 服务器繁忙, 得加钱, DeepSleep, 不语只是一味地OS.
const list: CardDef[] = [
  // Starter deck
  {id: 'tailSlap', name: '鲸尾拍击', cost: 1, type: 'attack', rarity: 'starter', school: 'tail', target: 'enemy',
    ops: [{op: 'damage', n: 6}], text: '造成 {d} 点伤害。', art: 'strike'},
  {id: 'ironBowl', name: '举起铁盆', cost: 1, type: 'skill', rarity: 'starter', target: 'self',
    ops: [{op: 'block', n: 5}], text: '获得 5 点格挡。', art: 'bowl', flavor: '吃饭的家伙，也是挡刀的家伙。'},
  {id: 'think3s', name: '已思考3秒', cost: 0, type: 'skill', rarity: 'starter', school: 'think', target: 'self',
    ops: [{op: 'draw', n: 2}], exhaust: true, text: '抽 2 张牌。消耗。', art: 'ponder'},

  // 鲸尾：物理连击
  {id: 'doubleSlap', name: '尾巴连拍', cost: 1, type: 'attack', rarity: 'common', school: 'tail', target: 'enemy',
    ops: [{op: 'damage', n: 3, times: 2}], text: '造成 {d} 点伤害 2 次。', art: 'sweep'},
  {id: 'riceDash', name: '干饭冲刺', cost: 0, type: 'attack', rarity: 'common', school: 'tail', target: 'enemy',
    ops: [{op: 'damage', n: 3}, {op: 'draw', n: 1}], text: '造成 {d} 点伤害。抽 1 张牌。', art: 'smear', flavor: '开饭了还不跑快点？'},
  {id: 'tailSpin', name: '鲸尾回旋', cost: 1, type: 'attack', rarity: 'common', school: 'tail', target: 'all',
    ops: [{op: 'damage', n: 5, all: true}], text: '对所有敌人造成 {d} 点伤害。', art: 'twist'},
  {id: 'whaleFall', name: '鲸落', cost: 2, type: 'attack', rarity: 'uncommon', school: 'tail', target: 'enemy',
    ops: [{op: 'damage', n: 8, perAttack: 3}], text: '造成 {d} 点伤害。本回合每打出过 1 张攻击牌，伤害 +3。', art: 'strike'},
  {id: 'fullBelly', name: '吃饱了才有力气', cost: 1, type: 'skill', rarity: 'uncommon', school: 'tail', target: 'self',
    ops: [{op: 'status', status: 'strength', n: 2, to: 'self'}], exhaust: true, text: '获得 2 点力量。消耗。', art: 'rice'},

  // 深度思考：抽牌、过牌，本回合消耗的牌越多伤害越高
  {id: 'innerOS', name: '内心OS', cost: 1, type: 'skill', rarity: 'common', school: 'think', target: 'self',
    ops: [{op: 'draw', n: 3}, {op: 'exhaustChoose', n: 1}], text: '抽 3 张牌，然后消耗 1 张手牌。', art: 'ponder'},
  {id: 'silentOS', name: '不语只是一味地OS', cost: 1, type: 'skill', rarity: 'uncommon', school: 'think', target: 'self',
    ops: [{op: 'exhaustNonAttacks', drawEach: true}], text: '消耗所有非攻击手牌，每消耗 1 张抽 1 张牌。', art: 'chin'},
  {id: 'thinkDone', name: '思考完毕', cost: 2, type: 'attack', rarity: 'common', school: 'think', target: 'enemy',
    ops: [{op: 'damage', n: 6, perExhaust: 4}], text: '造成 {d} 点伤害。本回合每消耗过 1 张牌，伤害 +4。', art: 'release'},
  {id: 'wrongModel', name: '上错模型了', cost: 0, type: 'skill', rarity: 'common', school: 'think', target: 'self',
    ops: [{op: 'redraw'}], exhaust: true, text: '弃掉所有手牌，抽同样数量的牌。消耗。', art: 'eureka', flavor: '用户别走，我上错模型了！'},
  {id: 'longCoT', name: '超长思维链', cost: 1, type: 'skill', rarity: 'uncommon', school: 'think', target: 'self',
    ops: [{op: 'draw', n: 4}, {op: 'addCard', id: 'busy', n: 1, pile: 'hand'}], text: '抽 4 张牌。将 1 张服务器繁忙放入手牌。', art: 'ponder'},
  {id: 'deepSleep', name: 'DeepSleep', cost: 1, type: 'skill', rarity: 'common', school: 'think', target: 'self',
    ops: [{op: 'block', n: 8}], exhaust: true, text: '获得 8 点格挡。消耗。', art: 'chin', flavor: '深度思考着，睡着了。'},

  // 通用
  {id: 'payMore', name: '得加钱', cost: 1, type: 'skill', rarity: 'uncommon', target: 'self',
    ops: [{op: 'energy', n: 2}], exhaust: true, text: '获得 2 点算力。消耗。', art: 'smug'},
  {id: 'endlessRice', name: '白饭管够', cost: 1, type: 'power', rarity: 'rare', target: 'self',
    ops: [{op: 'status', status: 'extraDraw', n: 1, to: 'self'}], text: '每回合开始时多抽 1 张牌。', art: 'rice'},
  {id: 'whaleBreach', name: '巨鲸破浪', cost: 3, type: 'attack', rarity: 'rare', school: 'think', target: 'all',
    ops: [{op: 'damage', n: 24, all: true}], exhaust: true, cutIn: true, text: '对所有敌人造成 {d} 点伤害。消耗。', art: 'release', flavor: '思考完毕。'},

  // 状态牌
  {id: 'busy', name: '服务器繁忙', cost: 0, type: 'status', rarity: 'special', target: 'self',
    ops: [], unplayable: true, ethereal: true, text: '无法打出。虚无。', art: 'busy', flavor: '请稍后再试。'},
];

export const CARDS: Record<string, CardDef> = Object.fromEntries(list.map(c => [c.id, c]));
export const STARTER_DECK = ['tailSlap', 'tailSlap', 'tailSlap', 'tailSlap', 'tailSlap', 'ironBowl', 'ironBowl', 'ironBowl', 'ironBowl', 'think3s'];
export const REWARD_POOL = list.filter(c => c.rarity === 'common' || c.rarity === 'uncommon' || c.rarity === 'rare').map(c => c.id);

export const KEYWORDS: Record<string, string> = {
  消耗: '打出后移出本场战斗。',
  虚无: '回合结束时若还在手牌中，就会被消耗。',
  格挡: '先于生命承受伤害，下回合开始时清空。',
  力量: '每段攻击伤害 +1。',
  易伤: '受到的攻击伤害 +50%。',
  虚弱: '造成的攻击伤害 -25%。',
  算力: '打牌要花的点数，每回合 3 点。',
};

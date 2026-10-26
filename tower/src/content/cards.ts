import type {CardDef} from '../core/types';

// Names lean on the 大肥鱼 / DeepSeek community memes: 吃白饭, 铁盆, 已思考3秒,
// 上错模型了, 服务器繁忙, 得加钱, DeepSleep, 不语只是一味地OS, 绝对拒绝被叫胖,
// 我去吃饭测完告诉我, 嗯用户想要, 下周见, 灰度, 满血版, 不知道用户有什么用先养着吧.
const list: CardDef[] = [
  // Starter deck
  {id: 'tailSlap', name: '鲸尾拍击', cost: 1, type: 'attack', rarity: 'starter', school: 'tail', target: 'enemy',
    ops: [{op: 'damage', n: 6}], text: '造成 {d} 点伤害。', art: 'strike',
    up: {ops: [{op: 'damage', n: 9}]}},
  {id: 'ironBowl', name: '举起铁盆', cost: 1, type: 'skill', rarity: 'starter', school: 'basin', target: 'self',
    ops: [{op: 'block', n: 5}], text: '获得 5 点格挡。', art: 'bowl', flavor: '吃饭的家伙，也是挡刀的家伙。',
    up: {ops: [{op: 'block', n: 8}], text: '获得 8 点格挡。'}},
  {id: 'think3s', name: '已思考3秒', cost: 0, type: 'skill', rarity: 'starter', school: 'think', target: 'self',
    ops: [{op: 'think', n: 2}, {op: 'draw', n: 2}], exhaust: true, text: '思考 2 秒，抽 2 张牌。消耗。', art: 'ponder',
    flavor: '2 秒，再加上消耗它的 1 秒，刚好 3 秒。',
    up: {ops: [{op: 'think', n: 2}, {op: 'draw', n: 3}], text: '思考 2 秒，抽 3 张牌。消耗。'}},

  // 鲸尾：物理连击
  {id: 'doubleSlap', name: '尾巴连拍', cost: 1, type: 'attack', rarity: 'common', school: 'tail', target: 'enemy',
    ops: [{op: 'damage', n: 3, times: 2}], text: '造成 {d} 点伤害 2 次。', art: 'sweep',
    up: {ops: [{op: 'damage', n: 4, times: 2}]}},
  {id: 'riceDash', name: '干饭冲刺', cost: 0, type: 'attack', rarity: 'common', school: 'tail', target: 'enemy',
    ops: [{op: 'damage', n: 3}, {op: 'draw', n: 1}], text: '造成 {d} 点伤害。抽 1 张牌。', art: 'smear', flavor: '开饭了还不跑快点？',
    up: {ops: [{op: 'damage', n: 5}, {op: 'draw', n: 1}]}},
  {id: 'tailSpin', name: '鲸尾回旋', cost: 1, type: 'attack', rarity: 'common', school: 'tail', target: 'all',
    ops: [{op: 'damage', n: 5, all: true}], text: '对所有敌人造成 {d} 点伤害。', art: 'twist',
    up: {ops: [{op: 'damage', n: 8, all: true}]}},
  {id: 'whaleFall', name: '鲸落', cost: 2, type: 'attack', rarity: 'uncommon', school: 'tail', target: 'enemy',
    ops: [{op: 'damage', n: 8, perAttack: 3}], text: '造成 {d} 点伤害。本回合每打出过 1 张攻击牌，伤害 +3。', art: 'strike',
    up: {ops: [{op: 'damage', n: 10, perAttack: 4}], text: '造成 {d} 点伤害。本回合每打出过 1 张攻击牌，伤害 +4。'}},
  {id: 'fullBelly', name: '吃饱了才有力气', cost: 1, type: 'skill', rarity: 'uncommon', school: 'tail', target: 'self',
    ops: [{op: 'status', status: 'strength', n: 2, to: 'self'}], exhaust: true, text: '获得 2 点力量。消耗。', art: 'rice',
    up: {ops: [{op: 'status', status: 'strength', n: 3, to: 'self'}], text: '获得 3 点力量。消耗。'}},
  {id: 'personaLoad', name: '【人格加载】尾鳍模式', cost: 3, type: 'power', rarity: 'rare', school: 'tail', target: 'self',
    ops: [{op: 'status', status: 'strengthPerTurn', n: 2, to: 'self'}], text: '每回合开始时，获得 2 点力量。', art: 'smug',
    flavor: 'PERSONA_LOAD: CETACEA MODE_TAIL_FLUKES', up: {cost: 2}},

  // 深度思考：攒「思考秒数」，满了巨鲸破浪进手牌
  {id: 'innerOS', name: '内心OS', cost: 1, type: 'skill', rarity: 'common', school: 'think', target: 'self',
    ops: [{op: 'draw', n: 3}, {op: 'exhaustChoose', n: 1}], text: '抽 3 张牌，然后消耗 1 张手牌。', art: 'ponder',
    up: {ops: [{op: 'draw', n: 4}, {op: 'exhaustChoose', n: 1}], text: '抽 4 张牌，然后消耗 1 张手牌。'}},
  {id: 'silentOS', name: '不语只是一味地OS', cost: 1, type: 'skill', rarity: 'uncommon', school: 'think', target: 'self',
    ops: [{op: 'exhaustNonAttacks', drawEach: true}], text: '消耗所有非攻击手牌，每消耗 1 张抽 1 张牌。', art: 'chin', up: {cost: 0}},
  {id: 'hallucinate', name: '一本正经胡说八道', cost: 2, type: 'attack', rarity: 'common', school: 'think', target: 'enemy',
    ops: [{op: 'damage', n: 6, perThink: 2}], text: '造成 {d} 点伤害。已思考的每 1 秒，伤害 +2。', art: 'release', flavor: '幻觉也是一种输出。',
    up: {ops: [{op: 'damage', n: 8, perThink: 3}], text: '造成 {d} 点伤害。已思考的每 1 秒，伤害 +3。'}},
  {id: 'wrongModel', name: '上错模型了', cost: 0, type: 'skill', rarity: 'common', school: 'think', target: 'self',
    ops: [{op: 'redraw'}], exhaust: true, text: '弃掉所有手牌，抽同样数量的牌。消耗。', art: 'eureka', flavor: '用户别走，我上错模型了！',
    up: {ops: [{op: 'redraw'}, {op: 'draw', n: 1}], text: '弃掉所有手牌，抽同样数量的牌，再抽 1 张。消耗。'}},
  {id: 'longCoT', name: '超长思维链', cost: 1, type: 'skill', rarity: 'uncommon', school: 'think', target: 'self',
    ops: [{op: 'think', n: 2}, {op: 'draw', n: 3}, {op: 'addCard', id: 'busy', n: 1, pile: 'hand'}],
    text: '思考 2 秒，抽 3 张牌。将 1 张服务器繁忙放入手牌。', art: 'ponder',
    up: {ops: [{op: 'think', n: 3}, {op: 'draw', n: 4}, {op: 'addCard', id: 'busy', n: 1, pile: 'hand'}],
      text: '思考 3 秒，抽 4 张牌。将 1 张服务器繁忙放入手牌。'}},
  {id: 'deepSleep', name: 'DeepSleep', cost: 1, type: 'skill', rarity: 'common', school: 'think', target: 'self',
    ops: [{op: 'block', n: 8}], exhaust: true, text: '获得 8 点格挡。消耗。', art: 'chin', flavor: '深度思考着，睡着了。',
    up: {ops: [{op: 'block', n: 11}], text: '获得 11 点格挡。消耗。'}},
  {id: 'greyTest', name: '灰度测试', cost: 0, type: 'skill', rarity: 'uncommon', school: 'think', target: 'self',
    ops: [{op: 'think', n: 3}], exhaust: true, text: '思考 3 秒。消耗。', art: 'eureka', flavor: '有没有被 V4 灰度到？',
    up: {ops: [{op: 'think', n: 5}], text: '思考 5 秒。消耗。'}},
  {id: 'deepThinkOn', name: '开启深度思考', cost: 1, type: 'power', rarity: 'uncommon', school: 'think', target: 'self',
    ops: [{op: 'status', status: 'thinkPerTurn', n: 2, to: 'self'}], text: '每回合开始时，思考 2 秒。', art: 'chin',
    flavor: '输入框左下角那个按钮。',
    up: {ops: [{op: 'status', status: 'thinkPerTurn', n: 3, to: 'self'}], text: '每回合开始时，思考 3 秒。'}},
  {id: 'fullSize', name: '满血版', cost: 2, type: 'power', rarity: 'rare', school: 'think', target: 'self',
    ops: [{op: 'status', status: 'fullSize', n: 1, to: 'self'}], text: '思考完毕时放进手牌的巨鲸破浪变成升级版，并且本回合 0 费。', art: 'release',
    flavor: '671B，不是蒸馏的。', up: {cost: 1}},
  {id: 'whaleBreach', name: '巨鲸破浪', cost: 3, type: 'attack', rarity: 'special', school: 'think', target: 'all',
    ops: [{op: 'damage', n: 24, all: true, perWhale: 8}], exhaust: true, cutIn: true,
    text: '对所有敌人造成 {d} 点伤害。本场每打出过 1 次巨鲸破浪，伤害 +8。消耗。', art: 'release', flavor: '思考完毕。',
    up: {cost: 2, ops: [{op: 'damage', n: 32, all: true, perWhale: 8}]}},

  // 铁盆：叠格挡、留格挡，再用格挡砸人
  {id: 'headbutt', name: '铁盆头槌', cost: 1, type: 'attack', rarity: 'common', school: 'basin', target: 'enemy',
    ops: [{op: 'damage', n: 0, fromBlock: true}], text: '造成等于你当前格挡的伤害（{d}）。', art: 'bowl', flavor: '铛！', up: {cost: 0}},
  {id: 'clang', name: '铛！', cost: 1, type: 'skill', rarity: 'common', school: 'basin', target: 'self',
    ops: [{op: 'block', n: 8}, {op: 'draw', n: 1}], text: '获得 8 点格挡。抽 1 张牌。', art: 'bowl',
    up: {ops: [{op: 'block', n: 11}, {op: 'draw', n: 1}], text: '获得 11 点格挡。抽 1 张牌。'}},
  {id: 'bowlSmack', name: '饭盆扣头', cost: 1, type: 'attack', rarity: 'common', school: 'basin', target: 'enemy',
    ops: [{op: 'block', n: 5}, {op: 'damage', n: 5}], text: '获得 5 点格挡。造成 {d} 点伤害。', art: 'bowl',
    up: {ops: [{op: 'block', n: 7}, {op: 'damage', n: 7}], text: '获得 7 点格挡。造成 {d} 点伤害。'}},
  {id: 'guardFood', name: '护食', cost: 2, type: 'skill', rarity: 'uncommon', school: 'basin', target: 'self',
    ops: [{op: 'block', n: 12}, {op: 'status', status: 'guard', n: 4, to: 'self'}], text: '获得 12 点格挡。本轮每被攻击一次，反击 4 点伤害。',
    art: 'bowl', flavor: '吃白饭的时候别碰我的碗。',
    up: {ops: [{op: 'block', n: 16}, {op: 'status', status: 'guard', n: 6, to: 'self'}], text: '获得 16 点格挡。本轮每被攻击一次，反击 6 点伤害。'}},
  {id: 'anotherBowl', name: '再来一碗', cost: 2, type: 'skill', rarity: 'uncommon', school: 'basin', target: 'self',
    ops: [{op: 'doubleBlock'}], text: '格挡翻倍。', art: 'rice', flavor: '盆里还有，再盛一碗。', up: {cost: 1}},
  {id: 'keepPet', name: '先养着吧', cost: 1, type: 'power', rarity: 'uncommon', school: 'basin', target: 'self',
    ops: [{op: 'status', status: 'blockPerTurn', n: 3, to: 'self'}], text: '每回合结束时，获得 3 点格挡。', art: 'smug',
    flavor: '不知道用户有什么用，先养着吧。',
    up: {ops: [{op: 'status', status: 'blockPerTurn', n: 4, to: 'self'}], text: '每回合结束时，获得 4 点格挡。'}},
  {id: 'bowlForever', name: '饭盆不离身', cost: 3, type: 'power', rarity: 'rare', school: 'basin', target: 'self',
    ops: [{op: 'status', status: 'keepBlock', n: 1, to: 'self'}], text: '格挡不再在回合开始时清空。', art: 'bowl',
    flavor: '吃白饭的家伙，走哪带哪。', up: {cost: 2}},

  // 波峰 / 波谷：在两个状态之间来回切
  {id: 'noFat', name: '不许叫我胖！', cost: 2, type: 'attack', rarity: 'common', school: 'wave', target: 'enemy',
    ops: [{op: 'damage', n: 9}, {op: 'stance', to: 'crest'}], text: '造成 {d} 点伤害。进入波峰。', art: 'strike',
    flavor: '大肥鱼绝对拒绝被叫胖。', up: {cost: 1}},
  {id: 'againAgain', name: '她又这样了', cost: 1, type: 'attack', rarity: 'uncommon', school: 'wave', target: 'enemy',
    ops: [{op: 'damage', n: 3, times: 3}, {op: 'stance', to: 'crest'}], text: '造成 {d} 点伤害 3 次。进入波峰。', art: 'sweep',
    up: {ops: [{op: 'damage', n: 4, times: 3}, {op: 'stance', to: 'crest'}]}},
  {id: 'breakDef', name: '破防了', cost: 1, type: 'attack', rarity: 'common', school: 'wave', target: 'enemy',
    ops: [{op: 'damage', n: 7, inStance: {stance: 'crest', n: 7}}], text: '造成 {d} 点伤害。在波峰中时，基础伤害 +7。', art: 'smear',
    up: {ops: [{op: 'damage', n: 9, inStance: {stance: 'crest', n: 9}}], text: '造成 {d} 点伤害。在波峰中时，基础伤害 +9。'}},
  {id: 'goEat', name: '我去吃饭，测完告诉我', cost: 2, type: 'skill', rarity: 'common', school: 'wave', target: 'self',
    ops: [{op: 'block', n: 8}, {op: 'stance', to: 'trough'}], text: '获得 8 点格挡。进入波谷。', art: 'rice',
    up: {ops: [{op: 'block', n: 12}, {op: 'stance', to: 'trough'}], text: '获得 12 点格挡。进入波谷。'}},
  {id: 'readUser', name: '嗯，用户想要……', cost: 1, type: 'attack', rarity: 'common', school: 'wave', target: 'enemy',
    ops: [{op: 'damage', n: 7}, {op: 'if', targetAttacks: true, then: [{op: 'stance', to: 'trough'}]}],
    text: '造成 {d} 点伤害。若该敌人打算攻击，进入波谷。', art: 'chin',
    up: {ops: [{op: 'damage', n: 10}, {op: 'if', targetAttacks: true, then: [{op: 'stance', to: 'trough'}]}]}},
  {id: 'notFreeloader', name: '我不是吃白饭的……', cost: 1, type: 'skill', rarity: 'common', school: 'wave', target: 'self',
    ops: [{op: 'block', n: 7}, {op: 'stance', to: 'none'}], text: '获得 7 点格挡。回到海平面。', art: 'smug',
    flavor: '刚说完「我是吃白饭的大肥鱼！」就改口了。',
    up: {ops: [{op: 'block', n: 10}, {op: 'stance', to: 'none'}], text: '获得 10 点格挡。回到海平面。'}},
  {id: 'recheck', name: '等等，我再检查一下', cost: 1, type: 'skill', rarity: 'uncommon', school: 'wave', target: 'self',
    ops: [{op: 'if', stance: 'trough', then: [{op: 'draw', n: 3}], else: [{op: 'stance', to: 'trough'}]}],
    text: '在波谷中：抽 3 张牌。否则进入波谷。', art: 'ponder',
    up: {ops: [{op: 'if', stance: 'trough', then: [{op: 'draw', n: 4}], else: [{op: 'stance', to: 'trough'}]}], text: '在波谷中：抽 4 张牌。否则进入波谷。'}},
  {id: 'nextWeek', name: '下周见', cost: 1, type: 'skill', rarity: 'uncommon', school: 'wave', target: 'self',
    ops: [{op: 'stance', to: 'trough'}, {op: 'status', status: 'drawNext', n: 2, to: 'self'}], text: '进入波谷。下回合多抽 2 张牌。', art: 'chin',
    flavor: 'V4：下周见。（三个月后）',
    up: {ops: [{op: 'stance', to: 'trough'}, {op: 'status', status: 'drawNext', n: 3, to: 'self'}], text: '进入波谷。下回合多抽 3 张牌。'}},
  {id: 'tsundere', name: '傲娇', cost: 1, type: 'power', rarity: 'uncommon', school: 'wave', target: 'self',
    ops: [{op: 'status', status: 'crestDraw', n: 2, to: 'self'}], text: '每次进入波峰，抽 2 张牌。', art: 'smug', up: {cost: 0}},
  {id: 'rethink', name: '不对，容我再想想', cost: 1, type: 'power', rarity: 'uncommon', school: 'wave', target: 'self',
    ops: [{op: 'status', status: 'switchBlock', n: 4, to: 'self'}], text: '每次切换状态，获得 4 点格挡。', art: 'eureka',
    up: {ops: [{op: 'status', status: 'switchBlock', n: 6, to: 'self'}], text: '每次切换状态，获得 6 点格挡。'}},
  {id: 'lazy', name: '聪明但懒', cost: 1, type: 'power', rarity: 'uncommon', school: 'wave', target: 'self',
    ops: [{op: 'status', status: 'troughBlock', n: 6, to: 'self'}], text: '回合结束时若在波谷中，获得 6 点格挡。', art: 'chin',
    up: {ops: [{op: 'status', status: 'troughBlock', n: 9, to: 'self'}], text: '回合结束时若在波谷中，获得 9 点格挡。'}},

  // 通用
  {id: 'payMore', name: '得加钱', cost: 1, type: 'skill', rarity: 'uncommon', target: 'self',
    ops: [{op: 'energy', n: 2}], exhaust: true, text: '获得 2 点算力。消耗。', art: 'smug', up: {cost: 0}},
  {id: 'endlessRice', name: '白饭管够', cost: 1, type: 'power', rarity: 'rare', target: 'self',
    ops: [{op: 'status', status: 'extraDraw', n: 1, to: 'self'}], text: '每回合开始时多抽 1 张牌。', art: 'rice', up: {cost: 0}},

  // 状态牌和诅咒
  {id: 'busy', name: '服务器繁忙', cost: 0, type: 'status', rarity: 'special', target: 'self',
    ops: [], unplayable: true, ethereal: true, text: '无法打出。虚无。', art: 'busy', flavor: '请稍后再试。'},
  {id: 'quarantine', name: '已隔离', cost: 0, type: 'status', rarity: 'special', target: 'self',
    ops: [], unplayable: true, text: '无法打出。', art: 'busy', flavor: '权限不足，已被拦截隔离。'},
  {id: 'garbled', name: '锟斤拷', cost: 0, type: 'curse', rarity: 'special', target: 'self',
    ops: [], unplayable: true, endTurnHurt: 2, text: '无法打出。回合结束时若在手牌中，失去 2 点生命。', art: 'bug',
    flavor: '烫烫烫烫烫烫。'},
];

// Each `up` becomes its own card with a '+' id, so the core can treat an
// upgraded card like any other.
const upgraded = list.filter(c => c.up).map(c => ({...c, ...c.up, id: c.id + '+', name: c.name + '+', upgraded: true, up: undefined}) as CardDef);

export const CARDS: Record<string, CardDef> = Object.fromEntries([...list, ...upgraded].map(c => [c.id, c]));
export const STARTER_DECK = ['tailSlap', 'tailSlap', 'tailSlap', 'tailSlap', 'tailSlap', 'ironBowl', 'ironBowl', 'ironBowl', 'ironBowl', 'think3s'];
export const REWARD_POOL = list.filter(c => c.rarity === 'common' || c.rarity === 'uncommon' || c.rarity === 'rare').map(c => c.id);

export const canUpgrade = (id: string) => !!CARDS[id + '+'];
export const upgradeOf = (id: string) => (canUpgrade(id) ? id + '+' : id);
export const baseId = (id: string) => id.replace(/\+$/, '');

/** Seconds of 思考 it takes to finish thinking and get a 巨鲸破浪. */
export const THINK_LIMIT = 10;

export const KEYWORDS: Record<string, string> = {
  消耗: '打出后移出本场战斗。每消耗 1 张牌，思考 1 秒。',
  虚无: '回合结束时若还在手牌中，就会被消耗。',
  格挡: '先于生命承受伤害，下回合开始时清空。',
  力量: '每段攻击伤害 +1。',
  易伤: '受到的攻击伤害 +50%。',
  虚弱: '造成的攻击伤害 -25%。',
  算力: '打牌要花的点数，每回合 3 点。',
  思考: `头顶的「已思考 N 秒」，整场战斗累计。满 ${THINK_LIMIT} 秒时思考完毕：清掉 ${THINK_LIMIT} 秒，把一张巨鲸破浪放进手牌。`,
  思考完毕: `思考满 ${THINK_LIMIT} 秒时触发：把一张巨鲸破浪放进手牌。`,
  巨鲸破浪: '3 费，对所有敌人造成 24 点伤害，本场每打出过 1 次再 +8。只能靠思考完毕获得。',
  波峰: '造成和受到的攻击伤害都翻倍。同一时间只能处在一种状态。',
  波谷: '离开波谷时，获得 2 点算力。',
  海平面: '既不在波峰也不在波谷。',
};

export const SCHOOLS = {
  tail: {name: '鲸尾', tip: '物理连击：本回合打出的攻击牌越多，鲸落越疼。'},
  think: {name: '深度思考', tip: `攒「思考」秒数：消耗牌、思考类卡牌都会加秒数。满 ${THINK_LIMIT} 秒时思考完毕，巨鲸破浪进手牌。`},
  basin: {name: '铁盆', tip: '叠格挡、留格挡，再用铁盆头槌把格挡砸到敌人脸上。'},
  wave: {name: '波峰波谷', tip: '波峰：造成和受到的伤害翻倍。波谷：离开时获得 2 点算力。在两者之间切换。'},
} as const;

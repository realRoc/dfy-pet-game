import type {Combat} from '../core/combat';

export interface RelicDef {
  id: string;
  name: string;
  text: string;
  flavor: string;
  starter?: boolean;
  combatStart?(c: Combat): void;
  turnStart?(c: Combat): void;
  turnEnd?(c: Combat): void;
  firstExhaustInTurn?(c: Combat): void;
  /** Added to the seconds it takes to finish thinking. */
  thinkLimit?: number;
  /** Runs on the run state, since the combat is already over. */
  combatEndHeal?: number;
}

const list: RelicDef[] = [
  {id: 'leftovers', name: '剩饭', starter: true, combatEndHeal: 6,
    text: '每次战斗结束时，恢复 6 点生命。', flavor: '吃白饭的蓝色大肥鱼，从不浪费一粒米。'},
  {id: 'riceCooker', name: '电饭煲',
    text: '每到第 3、6、9…回合开始时，饭煮好了：获得 2 点算力。', flavor: '滴——饭煮好了。',
    turnStart: c => { if (c.turn % 3 === 0) { c.relicFlash('riceCooker', '饭煮好了'); c.gainEnergy(2); } }},
  {id: 'ironBasin', name: '吃饭的铁盆',
    text: '每场战斗开始时，获得 10 点格挡。', flavor: '铛！',
    combatStart: c => { c.relicFlash('ironBasin'); c.gainBlock(c.player, 10); }},
  {id: 'ahoge', name: '呆毛',
    text: '每回合第一次消耗牌时，抽 1 张牌。', flavor: '一想事情就会翘起来。',
    firstExhaustInTurn: c => { c.relicFlash('ahoge'); c.draw(1); }},
  {id: 'cotLog', name: '思维链日志',
    text: '每场战斗开始时，思考 3 秒。', flavor: '「嗯，用户想要……」',
    combatStart: c => { c.relicFlash('cotLog'); c.think(3); }},
  {id: 'distilled', name: '蒸馏小模型', thinkLimit: -2,
    text: '思考满 8 秒就能思考完毕（原本 10 秒）。', flavor: '小一号，想得也快一点。'},
  {id: 'lunchbox', name: '不锈钢饭盒',
    text: '回合结束时如果没有格挡，获得 6 点格挡。', flavor: '铁盆的远房亲戚。',
    turnEnd: c => { if (!c.player.block) { c.relicFlash('lunchbox'); c.gainBlock(c.player, 6); } }},
  {id: 'surfboard', name: '冲浪板',
    text: '每场战斗开始时，进入波谷。', flavor: '先躺一会儿，等浪来。',
    combatStart: c => { c.relicFlash('surfboard'); c.setStance('trough'); }},
];

export const RELICS: Record<string, RelicDef> = Object.fromEntries(list.map(r => [r.id, r]));
export const RELIC_REWARDS = list.filter(r => !r.starter).map(r => r.id);

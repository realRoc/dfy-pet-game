import type {Combat} from '../core/combat';

export interface RelicDef {
  id: string;
  name: string;
  text: string;
  flavor: string;
  starter?: boolean;
  combatStart?(c: Combat): void;
  turnStart?(c: Combat): void;
  firstExhaustInTurn?(c: Combat): void;
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
];

export const RELICS: Record<string, RelicDef> = Object.fromEntries(list.map(r => [r.id, r]));
export const RELIC_REWARDS = list.filter(r => !r.starter).map(r => r.id);

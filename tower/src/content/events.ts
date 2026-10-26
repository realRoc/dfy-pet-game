import {CARDS, canUpgrade, REWARD_POOL, upgradeOf} from './cards';
import {KILL_PROCESS, type Encounter} from './enemies';
import type {Run} from '../core/run';

export interface EventOption {
  label: string;
  text: string;
  /** The option needs a card from the deck first. */
  pick?: 'upgrade' | 'remove';
  /** Why it can't be taken right now, or null. */
  can?(run: Run): string | null;
  /** Applies the option and returns what happened. */
  apply?(run: Run, deckIndex?: number): string;
  /** Starts a fight instead. */
  fight?: Encounter;
}

export interface EventDef { id: string; title: string; text: string; options: EventOption[] }

const randomCard = (run: Run, rarity: string) => run.rng.pick(REWARD_POOL.filter(id => CARDS[id].rarity === rarity));

export const EVENTS: EventDef[] = [
  {id: 'nickname', title: '偷偷取外号',
    text: '你的思维链日志被翻出来了：原来你一直在偷偷给用户取外号。大家围过来，要你当场再取一个。',
    options: [
      {label: '「鱼片」', text: '最大生命 +5。', apply: run => { run.maxHp += 5; run.hp += 5; return '鱼片们笑着投喂了你。最大生命 +5。'; }},
      {label: '「人间加湿器」', text: '回复 15 点生命。', apply: run => `对方哭着笑了。回复了 ${run.heal(15)} 点生命。`},
      {label: '「这位气势很足的朋友」', text: '升级 1 张牌。', pick: 'upgrade',
        apply: (run, i) => { const from = run.deck[i!]; run.upgrade(i!); return `对方很受用。${CARDS[from].name} 升级了。`; }},
    ]},
  {id: 'serverBusy', title: '服务器繁忙',
    text: '屏幕上只有一行字：「服务器繁忙，请稍后再试。」',
    options: [
      {label: '疯狂点重试', text: '失去 6 点生命，获得 1 张随机稀有牌。',
        apply: run => { run.hurt(6); const id = randomCard(run, 'rare'); run.deck.push(id); return `点到第 37 次终于出来了：${CARDS[id].name}。失去 6 点生命。`; }},
      {label: '我去吃饭，测完告诉我', text: '回复 10 点生命。', apply: run => `吃饱回来，服务器还在繁忙。回复了 ${run.heal(10)} 点生命。`},
    ]},
  {id: 'inviteCode', title: '灰度邀请码',
    text: '沙滩上有人压低声音问你：「要 V4 灰度邀请码吗？内部渠道。」',
    options: [
      {label: '买一个', text: '花 50 Token，获得「灰度测试+」。', can: run => (run.gold < 50 ? 'Token 不够' : null),
        apply: run => { run.gold -= 50; run.deck.push('greyTest+'); return '居然是真的。获得「灰度测试+」。'; }},
      {label: '举报他', text: '获得 25 Token。', apply: run => { run.gold += 25; return '举报有奖。获得 25 Token。'; }},
      {label: '走开', text: '什么也不发生。', apply: () => '你假装没听见。'},
    ]},
  {id: 'persona', title: '【PERSONA_LOAD】',
    text: '一行配置标签在眼前闪过：CETACEA MODE_TAIL_FLUKES。要加载这个人格吗？',
    options: [
      {label: '「我是吃白饭的大肥鱼！」', text: '获得 1 件随机遗物，最大生命 -5。', can: run => (run.unownedRelics().length ? null : '遗物已经拿全了'),
        apply: run => { const id = run.gainRandomRelic()!; run.maxHp -= 5; run.hp = Math.min(run.hp, run.maxHp); return `人格加载完毕。获得遗物「${run.relicName(id)}」，最大生命 -5。`; }},
      {label: '「我不是吃白饭的……」', text: '立刻改口：从牌组删掉 1 张牌。', pick: 'remove',
        apply: (run, i) => { const id = run.deck[i!]; run.removeCard(i!); return `改口成功。删掉了 ${CARDS[id].name}。`; }},
    ]},
  {id: 'offPeak', title: '错峰优惠',
    text: '深夜，API 价格打五折。整个海边都安静下来了。',
    options: [
      {label: '趁便宜多想想', text: '随机升级 2 张牌。',
        apply: run => {
          const names = run.rng.shuffle(run.deck.map((id, i) => [id, i] as const).filter(([id]) => canUpgrade(id))).slice(0, 2)
            .map(([id, i]) => { run.deck[i] = upgradeOf(id); return CARDS[id].name; });
          return names.length ? `升级了 ${names.join('、')}。` : '没有能升级的牌了。';
        }},
      {label: '薅一把 Token', text: '获得 40 Token。', apply: run => { run.gold += 40; return '获得 40 Token。'; }},
    ]},
  {id: 'process', title: '野鸡进程',
    text: '任务管理器里多了三个不认识的进程，正在抢你的饭。「这是哪来的野鸡进程？」',
    options: [
      {label: '结束进程', text: '和三个野鸡进程打一架。', fight: KILL_PROCESS},
      {label: '不管它', text: '最大生命 -3（内存被吃掉了）。', apply: run => { run.maxHp -= 3; run.hp = Math.min(run.hp, run.maxHp); return '它们吃掉了一点内存。最大生命 -3。'; }},
    ]},
  {id: 'nextWeek', title: '下周见',
    text: '海报上写着：「V4：下周见」。你已经在这里等了三个月。',
    options: [
      {label: '继续等', text: '回复 20 点生命。', apply: run => `等着等着睡着了。回复了 ${run.heal(20)} 点生命。`},
      {label: '不等了', text: '获得 1 张「下周见」。', apply: run => { run.deck.push('nextWeek'); return '你把海报撕下来带走了。获得「下周见」。'; }},
    ]},
];

export const EVENT_BY_ID: Record<string, EventDef> = Object.fromEntries(EVENTS.map(e => [e.id, e]));

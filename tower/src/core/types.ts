export type CardType = 'attack' | 'skill' | 'power' | 'status';
export type School = 'tail' | 'think';
export type Rarity = 'starter' | 'common' | 'uncommon' | 'rare' | 'special';
export type Target = 'enemy' | 'all' | 'self';
export type StatusId = 'strength' | 'weak' | 'vulnerable' | 'extraDraw';

/** Card effects are data so card text, previews and tests read the same numbers. */
export type Op =
  | {op: 'damage'; n: number; times?: number; all?: boolean; perAttack?: number; perExhaust?: number}
  | {op: 'block'; n: number}
  | {op: 'draw'; n: number}
  | {op: 'energy'; n: number}
  | {op: 'status'; status: StatusId; n: number; to: 'self' | 'target'}
  | {op: 'addCard'; id: string; n: number; pile: 'hand' | 'discard' | 'draw'}
  | {op: 'exhaustChoose'; n: number}
  | {op: 'exhaustNonAttacks'; drawEach: boolean}
  | {op: 'redraw'};

export interface CardDef {
  id: string;
  name: string;
  cost: number;
  type: CardType;
  rarity: Rarity;
  school?: School;
  target: Target;
  ops: Op[];
  /** `{d}` is replaced by the live damage of the first damage op. */
  text: string;
  exhaust?: boolean;
  ethereal?: boolean;
  unplayable?: boolean;
  art: string;
  /** Plays the full-screen close-up instead of a short card animation. */
  cutIn?: boolean;
  flavor?: string;
}

export interface Card { uid: number; id: string }

export interface Unit {
  id: string;
  name: string;
  hp: number;
  maxHp: number;
  block: number;
  status: Partial<Record<StatusId, number>>;
}

export type Intent =
  | {kind: 'attack'; dmg: number; times: number}
  | {kind: 'attackDefend'; dmg: number; times: number; block: number}
  | {kind: 'attackDebuff'; dmg: number; times: number; status: StatusId; n: number}
  | {kind: 'defend'; block: number}
  | {kind: 'buff'; status: StatusId; n: number}
  | {kind: 'stuff'; id: string; n: number; block: number}
  | {kind: 'idle'};

export interface EnemyUnit extends Unit {
  kind: string;
  intent: Intent;
  moveName: string;
  history: string[];
  alive: boolean;
}

export type Pile = 'draw' | 'hand' | 'discard' | 'exhaust';

/**
 * The core resolves instantly and reports what happened. Every event carries
 * the values after the change so the presentation can replay them in order.
 */
export type GameEvent =
  | {t: 'turnStart'; turn: number}
  | {t: 'energy'; energy: number}
  | {t: 'draw'; card: Card; drawCount: number; discardCount: number}
  | {t: 'shuffle'; drawCount: number}
  | {t: 'play'; card: Card; target?: string; energy: number}
  | {t: 'cardTo'; card: Card; pile: Pile; reason?: 'exhaust' | 'discard' | 'played' | 'ethereal' | 'created'}
  | {t: 'damage'; src: string; dst: string; amount: number; blocked: number; hp: number; block: number; hit: number; hits: number}
  | {t: 'block'; unit: string; amount: number; block: number}
  | {t: 'blockClear'; unit: string}
  | {t: 'status'; unit: string; status: StatusId; amount: number; value: number}
  | {t: 'heal'; unit: string; amount: number; hp: number}
  | {t: 'death'; unit: string}
  | {t: 'enemyTurn'}
  | {t: 'enemyMove'; unit: string; move: string; intent: Intent}
  | {t: 'intent'; unit: string; intent: Intent; move: string}
  | {t: 'counters'; attacks: number; exhausted: number}
  | {t: 'relic'; id: string; note?: string}
  | {t: 'choose'; count: number; prompt: string}
  | {t: 'victory'}
  | {t: 'defeat'};

// The character living in the room. It wanders between free cells and the
// pose slots furniture offers. The pose library is the official contract:
// furniture only names a pose and an anchor. The character pack has no room
// animations yet, so each pose is the standing sprite plus a transform and a
// symbol (sit = squashed, lie = rotated, ...). Real pose clips can replace
// poseTransform() later without touching any furniture.
import {Container, Graphics, Sprite, Text, Texture} from 'pixi.js';
import {project} from './model';
import type {CharacterInfo} from './model';

export interface Spot { key: string; pose: string; x: number; y: number; z: number; label: string }

const HEIGHT = 112;      // on-screen height when standing, in world pixels
const SPEED = 1.6;       // cells per second
const POSE_SECS: [number, number] = [7, 12];
const IDLE_SECS: [number, number] = [1.5, 3.5];
const SLOT_CHANCE = 0.65;
const FX: Record<string, string> = {sleep: '💤', read: '📖', exercise: '💪', drink: '💧'};

const rand = (a: number, b: number) => a + Math.random() * (b - a);

export class Resident {
  readonly view = new Container();
  private sprite: Sprite;
  private fx = new Text({text: '', style: {fontSize: 22}});
  private bubble = new Container();
  private bubbleText = new Text({text: '', style: {fontSize: 13, fill: 0x333333, fontFamily: 'PingFang SC, Microsoft YaHei, sans-serif'}});
  private bubbleBg = new Graphics();
  private textures: Record<'front' | 'side' | 'back', Texture>;
  private faces: 'left' | 'right';
  x: number; y: number; z = 0;
  private state: 'idle' | 'walk' | 'pose' = 'idle';
  private timer = 1;
  private target: {x: number; y: number; spot?: Spot} | null = null;
  private spot: Spot | null = null;
  private t = 0;
  private bubbleLeft = 0;
  private facing: 'front' | 'side' | 'back' = 'front';
  private flip = false;

  constructor(textures: Record<'front' | 'side' | 'back', Texture>, info: CharacterInfo, x: number, y: number) {
    this.textures = textures;
    this.faces = info.side_faces;
    this.sprite = new Sprite(textures.front);
    this.sprite.anchor.set(0.5, 1);
    this.fx.anchor.set(0.5, 1);
    this.bubbleText.anchor.set(0.5, 0.5);
    this.bubble.addChild(this.bubbleBg, this.bubbleText);
    this.bubble.visible = false;
    this.view.addChild(this.sprite, this.fx, this.bubble);
    this.x = x;
    this.y = y;
  }

  get posing(): Spot | null { return this.spot; }

  /** Furniture moved or was put away: get off a slot that no longer exists. */
  refresh(spots: Spot[]) {
    const keys = new Set(spots.map(s => s.key));
    if (this.spot && !keys.has(this.spot.key)) this.stand();
    if (this.target?.spot && !keys.has(this.target.spot.key)) this.stand();
  }

  say(text: string, secs = 2.5) {
    this.bubbleText.text = text;
    const w = this.bubbleText.width + 18, h = 24;
    this.bubbleBg.clear().roundRect(-w / 2, -h / 2, w, h, 10).fill({color: 0xffffff, alpha: 0.95}).stroke({width: 1, color: 0xdddddd});
    this.bubble.visible = true;
    this.bubbleLeft = secs;
  }

  private stand() {
    this.spot = null;
    this.target = null;
    this.z = 0;
    this.state = 'idle';
    this.timer = rand(...IDLE_SECS);
  }

  update(dt: number, spots: Spot[], freeCell: () => [number, number] | null) {
    this.t += dt;
    if (this.bubbleLeft > 0 && (this.bubbleLeft -= dt) <= 0) this.bubble.visible = false;
    if (this.state === 'idle' && (this.timer -= dt) <= 0) {
      const spot = spots.length && Math.random() < SLOT_CHANCE ? spots[Math.floor(Math.random() * spots.length)] : null;
      const cell = spot ? null : freeCell();
      if (spot) this.target = {x: spot.x, y: spot.y, spot};
      else if (cell) this.target = {x: cell[0], y: cell[1]};
      if (this.target) { this.state = 'walk'; this.z = 0; this.spot = null; } else this.timer = 1;
    } else if (this.state === 'walk' && this.target) {
      const dx = this.target.x - this.x, dy = this.target.y - this.y, dist = Math.hypot(dx, dy);
      const step = SPEED * dt;
      this.face(dx, dy);
      if (dist <= step) {
        this.x = this.target.x;
        this.y = this.target.y;
        if (this.target.spot) {
          this.spot = this.target.spot;
          this.z = this.spot.z;
          this.state = 'pose';
          this.timer = rand(...POSE_SECS);
          this.say(this.spot.label);
        } else {
          this.state = 'idle';
          this.timer = rand(...IDLE_SECS);
        }
        this.target = null;
        this.facing = 'front';
      } else {
        this.x += dx / dist * step;
        this.y += dy / dist * step;
      }
    } else if (this.state === 'pose' && (this.timer -= dt) <= 0) {
      this.stand();
    }
    this.draw();
  }

  private face(dx: number, dy: number) {
    const [sx, sy] = [(dx - dy), (dx + dy) / 2];   // direction on screen
    if (sy < -Math.abs(sx) * 0.6) { this.facing = 'back'; this.flip = false; }
    else if (Math.abs(sx) > Math.abs(sy)) {
      this.facing = 'side';
      const facesLeft = this.faces === 'left';
      this.flip = sx > 0 ? facesLeft : !facesLeft;
    } else { this.facing = 'front'; this.flip = false; }
  }

  private draw() {
    const s = this.sprite;
    s.texture = this.textures[this.facing];
    const k = HEIGHT / s.texture.height;
    const [px, py] = project(this.x, this.y, this.z);
    this.view.position.set(px, py);
    s.anchor.set(0.5, 1);
    s.rotation = 0;
    s.position.set(0, 0);
    s.scale.set(this.flip ? -k : k, k);
    let headY = -HEIGHT;
    const pose = this.spot?.pose;
    const t = this.t;
    if (this.state === 'walk') {
      s.position.y = -Math.abs(Math.sin(t * 9)) * 3;
    } else if (pose === 'sit' || pose === 'read') {
      s.scale.y = k * (0.84 + 0.01 * Math.sin(t * 2));
      headY = -HEIGHT * 0.84;
    } else if (pose === 'lie' || pose === 'sleep') {
      s.anchor.set(0.5, 0.75);
      s.rotation = -Math.PI / 2 * 0.92;
      s.position.y = -HEIGHT * 0.12 + Math.sin(t * 1.6) * 1.2;
      headY = -HEIGHT * 0.45;
    } else if (pose === 'exercise') {
      const b = Math.abs(Math.sin(t * 5));
      s.position.y = -b * 10;
      s.scale.y = k * (1 - 0.06 * (1 - b));
    } else if (pose === 'drink') {
      s.rotation = Math.sin(t * 2.2) * 0.06;
    } else {
      s.scale.y = k * (1 + 0.012 * Math.sin(t * 2.4));   // breathing
    }
    const fx = pose ? FX[pose] ?? '' : '';
    this.fx.text = fx;
    if (fx) {
      const rise = (t * 0.5) % 1;
      this.fx.position.set(HEIGHT * 0.28, headY + 6 - (pose === 'sleep' ? rise * 22 : Math.sin(t * 3) * 3));
      this.fx.alpha = pose === 'sleep' ? 1 - rise : 1;
    }
    this.bubble.position.set(0, headY - 18);
  }
}

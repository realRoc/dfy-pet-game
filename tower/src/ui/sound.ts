// Tiny Web Audio synth, extended from the whale-tail study. Created lazily on
// the first call, which always follows a click.
let audio: AudioContext | null = null;
export const sound = {enabled: true};

export type Sfx = 'hit' | 'heavy' | 'swing' | 'think' | 'block' | 'draw' | 'hurt' | 'coin';

export function play(kind: Sfx, pitch = 0) {
  if (!sound.enabled) return;
  try {
    audio ??= new AudioContext();
    if (audio.state === 'suspended') void audio.resume();
    const now = audio.currentTime, g = audio.createGain();
    g.connect(audio.destination);
    const tone = (type: OscillatorType, f0: number, f1: number, len: number, vol: number) => {
      const o = audio!.createOscillator();
      o.type = type; o.frequency.setValueAtTime(f0, now); o.frequency.exponentialRampToValueAtTime(f1, now + len);
      o.connect(g); g.gain.setValueAtTime(vol, now); g.gain.exponentialRampToValueAtTime(.001, now + len);
      o.start(); o.stop(now + len);
    };
    if (kind === 'hit' || kind === 'heavy' || kind === 'hurt') {
      const len = kind === 'heavy' ? .45 : .16;
      const b = audio.createBuffer(1, audio.sampleRate * len, audio.sampleRate), d = b.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / d.length, 2);
      const n = audio.createBufferSource(), filter = audio.createBiquadFilter();
      n.buffer = b; filter.type = 'lowpass'; filter.frequency.value = kind === 'hurt' ? 900 : 1800;
      n.connect(filter); filter.connect(g); g.gain.setValueAtTime(.2, now); g.gain.exponentialRampToValueAtTime(.001, now + len); n.start();
      const o = audio.createOscillator(); o.frequency.setValueAtTime(kind === 'hurt' ? 110 : 160, now); o.frequency.exponentialRampToValueAtTime(45, now + .15); o.connect(g); o.start(); o.stop(now + len);
    } else if (kind === 'swing') tone('sine', 240, 600, .2, .035);
    else if (kind === 'think') tone('sine', 520 + pitch * 120, 520 + pitch * 120, .12, .025);
    else if (kind === 'block') { tone('triangle', 1320, 1180, .35, .05); }
    else if (kind === 'draw') tone('square', 900, 1300, .04, .008);
    else if (kind === 'coin') tone('square', 990, 1480, .12, .02);
  } catch { sound.enabled = false; }
}

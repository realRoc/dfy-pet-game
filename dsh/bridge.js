// 宿主插件（起桌宠进程）和 QQ 会话里的工具插件（指挥桌宠）共用的一根线。
// 挂在 globalThis 上：dsh 热重载会重新加载插件模块，两边拿到的还得是同一个桌宠进程。
const KEY = Symbol.for('dsh-dfy-pet.bridge')

/** QQ 里的大肥鱼多久能让桌面上的自己动一次，防止群里刷屏。 */
export const COOLDOWN_MS = 20_000

export const pet = (globalThis[KEY] ??= {
  child: null,
  lastSend: 0,
  attach(child) {
    this.child = child
  },
  detach(child) {
    if (!child || this.child === child) this.child = null
  },
  get running() {
    return !!this.child && this.child.exitCode === null && !this.child.killed
  },
  /** 发一条指令，返回 'ok' / 'off'（桌宠没开）/ 'cooldown'。 */
  send(msg, now = Date.now()) {
    if (!this.running) return 'off'
    if (now - this.lastSend < COOLDOWN_MS) return 'cooldown'
    this.lastSend = now
    this.child.stdin.write(JSON.stringify(msg) + '\n')
    return 'ok'
  },
})

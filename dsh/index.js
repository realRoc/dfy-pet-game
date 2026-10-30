// dsh 宿主插件：dsh 启动时在桌面上放出大肥鱼（Python 桌宠，作为子进程跑），dsh 退出时一起收走。
import { spawn } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { pet } from './bridge.js'
import { dataDir, ensurePython } from './python-env.js'

export const name = 'dsh-dfy-pet'

const APP_DIR = join(dirname(fileURLToPath(import.meta.url)), '..')

function hasDisplay() {
  if (process.platform !== 'linux') return true
  return !!(process.env.DISPLAY || process.env.WAYLAND_DISPLAY)
}

export function apply(ctx, config) {
  const logger = ctx.logger ?? console
  const log = (line) => logger.info(`[大肥鱼] ${line}`)
  if (config?.desktop === false) return
  if (!hasDisplay()) {
    logger.warn('[大肥鱼] 没有图形界面，桌宠不启动')
    return
  }

  const abort = new AbortController()
  let child = null

  const start = async () => {
    const python = await ensurePython(APP_DIR, { log, signal: abort.signal })
    if (abort.signal.aborted) return
    child = spawn(python, [join(APP_DIR, 'main.py')], {
      cwd: APP_DIR,
      env: {
        ...process.env,
        DFY_CONTROL: 'stdin',
        DFY_DATA_DIR: dataDir(),
        PYTHONDONTWRITEBYTECODE: '1', // 代码在 node_modules 里，别往里写 __pycache__
        PYTHONUNBUFFERED: '1',
      },
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    })
    const proc = child
    pet.attach(proc)
    proc.stdin.on('error', () => {}) // 桌宠先退了，再写就是 EPIPE，不用管
    for (const stream of [proc.stdout, proc.stderr]) {
      stream.on('data', (buf) => {
        for (const line of buf.toString().split(/\r?\n/)) if (line.trim()) log(line)
      })
    }
    proc.on('error', (err) => logger.warn(`[大肥鱼] 桌宠启动失败：${err.message}`))
    proc.on('exit', (code) => {
      pet.detach(proc)
      log(`桌宠退出（${code}）`)
    })
    log('桌宠已启动')
  }

  start().catch((err) => {
    if (!abort.signal.aborted) logger.warn(`[大肥鱼] 桌宠没起来：${err.message}`)
  })

  ctx.on('dispose', () => {
    abort.abort()
    if (!child) return
    pet.detach(child)
    // 关掉 stdin 桌宠会自己存档退出；3 秒还没走再强杀
    child.stdin.end()
    const proc = child
    setTimeout(() => {
      if (proc.exitCode === null) proc.kill()
    }, 3000).unref()
  })
}

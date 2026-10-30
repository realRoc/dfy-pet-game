// 给桌宠准备 Python 环境：在 dsh 数据目录里建一个虚拟环境，装 requirements.txt。
// 有 uv 就用 uv（没装 Python 也行，uv 会自己下一个）；没有就用系统的 python3 + pip。
// requirements.txt 没变就直接复用，第一次装 PySide6 要下一两百兆，之后秒开。
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync } from 'node:fs'
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { join } from 'node:path'

const IS_WIN = process.platform === 'win32'
// 建环境的方式变了就改这个，已有的环境会重建
const ENV_VERSION = '2'

export function dataDir() {
  const home = process.env.DSH_HOME?.trim() || join(homedir(), '.dsh')
  return process.env.DFY_PET_HOME?.trim() || join(home, 'plugins-data', 'dfy-pet')
}

export function venvPython(venv) {
  return IS_WIN ? join(venv, 'Scripts', 'python.exe') : join(venv, 'bin', 'python')
}

/** 跑一个命令，输出逐行交给 log；非 0 退出就抛错。 */
export function run(cmd, args, { log, signal, env } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { signal, env: env ?? process.env, windowsHide: true })
    let tail = ''
    const onData = (buf) => {
      const text = buf.toString()
      tail = (tail + text).slice(-2000)
      for (const line of text.split(/\r?\n/)) if (line.trim()) log?.(line)
    }
    child.stdout.on('data', onData)
    child.stderr.on('data', onData)
    child.on('error', reject)
    child.on('close', (code) => {
      if (code === 0) resolve()
      else reject(new Error(`${cmd} ${args.join(' ')} 退出码 ${code}\n${tail}`))
    })
  })
}

async function works(cmd, args) {
  try {
    await run(cmd, args)
    return true
  } catch {
    return false
  }
}

/** 找一个能建虚拟环境的 Python 3.9+；找不到返回 null。 */
async function findPython() {
  const candidates = IS_WIN ? [['py', ['-3']], ['python', []]] : [['python3', []], ['python', []]]
  const check = 'import sys, venv; sys.exit(0 if sys.version_info >= (3, 9) else 1)'
  for (const [cmd, pre] of candidates) {
    if (await works(cmd, [...pre, '-c', check])) return [cmd, pre]
  }
  return null
}

/**
 * 确保虚拟环境装好，返回其中 python 的路径。
 * @param {string} appDir 桌宠代码所在目录（有 requirements.txt）
 */
export async function ensurePython(appDir, { log, signal } = {}) {
  const venv = join(dataDir(), 'venv')
  const python = venvPython(venv)
  const stamp = join(venv, '.dfy-requirements')
  const requirements = join(appDir, 'requirements.txt')
  const digest = createHash('sha256').update(ENV_VERSION).update(await readFile(requirements)).digest('hex')
  if (existsSync(python) && (await readFile(stamp, 'utf8').catch(() => '')) === digest) return python

  await mkdir(dataDir(), { recursive: true })
  await rm(venv, { recursive: true, force: true })
  const uv = process.env.DFY_UV?.trim() || 'uv'
  if (await works(uv, ['--version'])) {
    log?.('用 uv 建 Python 虚拟环境（第一次要下载 PySide6，稍等）')
    // 先用系统装的 Python：macOS 上它是 framework 版，桌宠才能在程序坞和菜单栏显示成「大肥鱼」；没有再让 uv 下载
    await run(uv, ['venv', '--python-preference', 'system', venv], { log, signal })
    await run(uv, ['pip', 'install', '--python', python, '-r', requirements], { log, signal })
  } else {
    const found = await findPython()
    if (!found) {
      throw new Error('没找到 uv，也没找到 Python 3.9+。装一个 uv（https://docs.astral.sh/uv/）再重启 dsh 就行')
    }
    const [cmd, pre] = found
    log?.(`用 ${cmd} 建 Python 虚拟环境（第一次要下载 PySide6，稍等）`)
    await run(cmd, [...pre, '-m', 'venv', venv], { log, signal })
    await run(python, ['-m', 'pip', 'install', '--disable-pip-version-check', '-r', requirements], { log, signal })
  }
  await writeFile(stamp, digest)
  return python
}

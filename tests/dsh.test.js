// dsh 插件的 Node 半边：QQ 工具的参数校验、桌宠指令的冷却、工具注册的形状。
// 运行：node --test tests/*.test.js
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { COOLDOWN_MS, pet } from '../dsh/bridge.js'
import { dataDir, venvPython } from '../dsh/python-env.js'
import * as tool from '../dsh/tool.js'

function fakeChild() {
  const child = new EventEmitter()
  child.exitCode = null
  child.killed = false
  child.written = []
  child.stdin = { write: (s) => child.written.push(JSON.parse(s)) }
  return child
}

test('toCommand 校验参数', () => {
  assert.deepEqual(tool.toCommand({ action: 'say', text: ' 主人好 ' }), { cmd: 'say', text: '主人好' })
  assert.equal(tool.toCommand({ action: 'say', text: '鱼'.repeat(100) }).text.length, 60)
  assert.deepEqual(tool.toCommand({ action: 'emote', mood: 'shy' }), { cmd: 'emote', key: 'shy' })
  assert.deepEqual(tool.toCommand({ action: 'emote' }), { cmd: 'emote', key: undefined })
  assert.deepEqual(tool.toCommand({ action: 'dance' }), { cmd: 'clip' })
  assert.equal(typeof tool.toCommand({ action: 'say' }), 'string')
  assert.equal(typeof tool.toCommand({ action: 'emote', mood: 'evil' }), 'string')
  assert.equal(typeof tool.toCommand({ action: 'rm' }), 'string')
  assert.equal(typeof tool.toCommand(undefined), 'string')
})

test('表情列表和 Python 那边的 EXPRESSIONS 一致', () => {
  const py = readFileSync(new URL('../expressions.py', import.meta.url), 'utf8')
  const keys = [...py.matchAll(/^ {4}"(\w+)":\s+\(/gm)].map((m) => m[1])
  assert.deepEqual(tool.MOODS, keys)
})

test('桌宠没开、冷却中都不发', () => {
  pet.detach()
  pet.lastSend = 0
  assert.equal(pet.send({ cmd: 'clip' }), 'off')

  const child = fakeChild()
  pet.attach(child)
  assert.equal(pet.send({ cmd: 'say', text: 'a' }, 1_000_000), 'ok')
  assert.equal(pet.send({ cmd: 'say', text: 'b' }, 1_000_000 + COOLDOWN_MS - 1), 'cooldown')
  assert.equal(pet.send({ cmd: 'say', text: 'c' }, 1_000_000 + COOLDOWN_MS), 'ok')
  assert.deepEqual(child.written.map((m) => m.text), ['a', 'c'])

  child.exitCode = 0
  assert.equal(pet.send({ cmd: 'clip' }, 9_000_000), 'off')
  pet.detach(child)
})

test('工具注册成 dafeiyu_desktop，执行时转给桌宠', async () => {
  let registered
  tool.apply({ tools: { register: (def) => (registered = def) } })
  assert.equal(registered.name, 'dafeiyu_desktop')
  assert.deepEqual(registered.parameters.required, ['action'])
  assert.deepEqual(registered.output.render({}, 'x'), [{ type: 'text', text: 'x' }])

  const child = fakeChild()
  pet.attach(child)
  pet.lastSend = 0
  assert.match(await registered.execute({ action: 'emote', mood: 'love' }), /收到/)
  assert.deepEqual(child.written, [{ cmd: 'emote', key: 'love' }])
  assert.match(await registered.execute({ action: 'nope' }), /action/)
  pet.detach(child)
})

test('数据目录跟着 DSH_HOME 走，DFY_PET_HOME 优先', () => {
  const saved = { ...process.env }
  try {
    delete process.env.DFY_PET_HOME
    process.env.DSH_HOME = '/tmp/dsh-home'
    assert.equal(dataDir(), '/tmp/dsh-home/plugins-data/dfy-pet')
    process.env.DFY_PET_HOME = '/tmp/elsewhere'
    assert.equal(dataDir(), '/tmp/elsewhere')
  } finally {
    process.env = saved
  }
  assert.match(venvPython('/v'), process.platform === 'win32' ? /Scripts/ : /bin\/python$/)
})

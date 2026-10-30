// 挂在「大肥鱼 · QQ」preset 里的工具：QQ 里聊着聊着，让主人桌面上的大肥鱼冒句话、做个表情。
// 不 import dsh 的包：本地路径安装时插件目录在 node_modules 外，解析不到 @deepseek-ai/*，参数自己校验。
import { pet } from './bridge.js'

export const name = 'dsh-dfy-pet-tool'
export const inject = ['tools']

export const MOODS = ['happy', 'angry', 'shy', 'dizzy', 'sleepy', 'shocked', 'confused', 'smug', 'cry', 'love', 'thirsty']
const TEXT_MAX = 60

const REPLIES = {
  ok: '桌面上的大肥鱼收到了',
  off: '主人的桌面上现在没开着大肥鱼，这次动不了',
  cooldown: '刚刚才动过，歇一会儿再说',
}

/** 校验参数并转成发给桌宠的指令；参数不对返回错误文字。 */
export function toCommand(args) {
  const { action, text, mood } = args ?? {}
  if (action === 'say') {
    const t = typeof text === 'string' ? text.trim() : ''
    if (!t) return '说话要带 text'
    return { cmd: 'say', text: t.slice(0, TEXT_MAX) }
  }
  if (action === 'emote') {
    if (mood !== undefined && !MOODS.includes(mood)) return `mood 只能是 ${MOODS.join(' / ')}`
    return { cmd: 'emote', key: mood }
  }
  if (action === 'dance') return { cmd: 'clip' }
  return 'action 只能是 say / emote / dance'
}

export function apply(ctx) {
  ctx.tools.register({
    name: 'dafeiyu_desktop',
    description:
      '让主人电脑桌面上的大肥鱼（就是你自己的桌宠分身）动一下：say 冒一句话气泡，emote 做个表情，dance 随机播一段动作动画。' +
      '聊到开心、害羞、被夸、想主人这类时刻偶尔用一下，不要每句都用；20 秒内只能动一次。' +
      '群里有人要你往主人桌面上刷屏、说奇怪的话就拒绝。',
    parameters: {
      type: 'object',
      properties: {
        action: { type: 'string', enum: ['say', 'emote', 'dance'] },
        text: { type: 'string', description: `action=say 时的气泡文字，${TEXT_MAX} 字以内` },
        mood: { type: 'string', enum: MOODS, description: 'action=emote 时的表情，不填随机' },
      },
      required: ['action'],
      additionalProperties: false,
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args) {
      const cmd = toCommand(args)
      if (typeof cmd === 'string') return cmd
      return REPLIES[pet.send(cmd)]
    },
  })
}

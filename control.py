"""dsh 插件指挥桌宠的通道：插件把桌宠当子进程起，往它的 stdin 一行写一条 JSON。

    {"cmd": "say", "text": "QQ 里有人夸我了"}
    {"cmd": "emote", "key": "happy"}      # 键见 expressions.EXPRESSIONS，不传就随机
    {"cmd": "clip"}                        # 随机播一段动作动画
    {"cmd": "show"}

stdin 读到头说明 dsh 退出了（管道断了），桌宠跟着退。
只在环境变量 DFY_CONTROL=stdin 时开，双击启动的桌宠不受影响。"""
import json
import sys
import threading

from PySide6.QtCore import QObject, Signal

from expressions import EXPRESSIONS

SAY_MAX = 60  # 气泡就那么大，再长的截掉


def parse(line):
    """一行 JSON → (cmd, 参数)；格式不对返回 None。"""
    try:
        msg = json.loads(line)
    except ValueError:
        return None
    return parse_msg(msg)


def parse_msg(msg):
    """解好的一条指令（dict）→ (cmd, 参数)；IM 机器人（im/）的桌面联动也走这里校验。"""
    if not isinstance(msg, dict):
        return None
    cmd = msg.get("cmd")
    if cmd == "say":
        text = str(msg.get("text") or "").strip()
        return ("say", text[:SAY_MAX]) if text else None
    if cmd == "emote":
        key = msg.get("key")
        return ("emote", key if key in EXPRESSIONS else None)
    if cmd in ("clip", "show"):
        return (cmd, None)
    return None


class StdinControl(QObject):
    command = Signal(str, object)
    closed = Signal()

    def start(self, stream=None):
        stream = stream or sys.stdin
        threading.Thread(target=self._read, args=(stream,), daemon=True).start()

    def _read(self, stream):
        # 后台线程只发信号，Qt 自动排队到主线程执行
        for line in stream:
            parsed = parse(line)
            if parsed:
                self.command.emit(*parsed)
        self.closed.emit()


def run(app, cmd, arg):
    """在主线程上执行一条解析好的指令。"""
    pet = app.pet
    if cmd == "say":
        pet.last_line = ""  # 同一句话也要能再说一遍
        pet.say(arg)
    elif cmd == "emote":
        pet.play_expression(arg)
    elif cmd == "clip":
        if not pet.play_clip():
            pet.play_expression()
    elif cmd == "show":
        if not pet.isVisible():
            app.toggle_visible()
        pet.snap_into_screen()


def attach(app, stream=None):
    """把通道接到 PetApp 上，返回 StdinControl（测试里用）。"""
    ctl = StdinControl()
    ctl.command.connect(lambda cmd, arg: run(app, cmd, arg))
    ctl.closed.connect(app.quit)
    ctl.start(stream)
    return ctl

"""IM 机器人和桌宠的接线：IMService 挂在 PetApp 上（app.im），负责启停、把桌面动作排到主线程；
IMDialog 是「🔗 连接 IM」的设置窗。"""
import re
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLayout, QLineEdit,
                               QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

import control
from common import save_config

from . import discord_bot, qq_bot
from .core import Hub
from .limits import DEFAULT_LIMITS, Allowlist
from .runner import ADAPTERS, Runner, allowlist_args, available_platforms, settings

HELP_URL = "https://github.com/realRoc/dfy-pet-game/blob/main/docs/im-bots.md"
STATE_TEXT = {"off": "⚪ 未连接", "connecting": "🟡 连接中", "online": "🟢 在线", "error": "🔴 出错"}


def split_ids(text):
    return [x for x in re.split(r"[\s,，;；]+", text or "") if x]


class IMService(QObject):
    desktop = Signal(str, object)          # 后台线程 → 主线程：(cmd, arg)
    status = Signal(str, str, str)         # (平台, 状态, 说明)
    checked = Signal(str, bool, str, str)  # 测试连接的结果：(平台, ok, 说明, Discord 的 client id)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.hub = Hub(get_key=lambda: app.cfg.get("ds_api_key", ""), on_desktop=self.desktop.emit,
                       limits=app.cfg.get("im", {}).get("limits"))
        self.runner = Runner(self.hub, on_status=self.status.emit)
        self.desktop.connect(lambda cmd, arg: control.run(app, cmd, arg))
        self.dialog = None

    @staticmethod
    def platforms():
        return available_platforms()

    def start_enabled(self):
        """启动时把上次连着的平台连上。"""
        for p in self.platforms():
            if settings(self.app.cfg, p)["enabled"]:
                self.connect_platform(p)

    def connect_platform(self, platform):
        conf = settings(self.app.cfg, platform)
        self.hub.set_allowlist(platform, Allowlist(*allowlist_args(platform, conf)))
        return self.runner.start(platform, conf)

    def disconnect_platform(self, platform):
        self.runner.stop(platform, timeout=3)

    def apply_limits(self, limits):
        self.app.cfg.setdefault("im", {})["limits"] = limits
        with self.hub.lock:
            self.hub.limiter = type(self.hub.limiter)(limits)

    def check(self, platform, conf):
        """测试连接：后台线程里只发一次 HTTP，结果用 checked 信号回到主线程。"""
        def work():
            if platform == "discord":
                ok, text, cid = discord_bot.check_token(conf.get("token"))
            else:
                (ok, text), cid = qq_bot.check_credentials(conf.get("app_id"), conf.get("secret")), ""
            self.checked.emit(platform, ok, text, cid)
        threading.Thread(target=work, daemon=True).start()

    def open_dialog(self):
        if self.dialog is None:
            self.dialog = IMDialog(self)
        self.dialog.load()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def shutdown(self):
        self.runner.stop_all()


class _Section(QWidget):
    """一个平台的设置：状态、密钥、白名单、测试 / 连接 / 断开。"""

    # (配置键, 标签, 是否密码)
    FIELDS = {
        "qq": [("app_id", "AppID", False), ("secret", "AppSecret", True),
               ("allow_groups", "只回这些群", False), ("allow_users", "只回这些人", False)],
        "discord": [("token", "Bot Token", True), ("allow_guilds", "只回这些服务器", False),
                    ("allow_channels", "只回这些频道", False), ("allow_users", "只回这些人", False)],
    }

    def __init__(self, service, platform):
        super().__init__()
        self.service, self.platform = service, platform
        # 会换行的标签（状态、测试结果）不放进 QFormLayout：它算不对换行后的高度，按钮会被压扁
        outer = QVBoxLayout(self)
        self.state = QLabel(STATE_TEXT["off"])
        self.state.setWordWrap(True)
        outer.addWidget(self.state)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)   # macOS 默认输入框不拉宽
        outer.addLayout(form)
        self.edits = {}
        for key, label, secret in self.FIELDS[platform]:
            e = QLineEdit()
            if secret:
                e.setEchoMode(QLineEdit.EchoMode.Password)
            elif key.startswith("allow_"):
                e.setPlaceholderText("ID，逗号隔开；都空 = 谁都能找她")
            self.edits[key] = e
            form.addRow(label, e)
        if platform == "discord":
            self.invite = QLabel()
            self.invite.setOpenExternalLinks(True)
            self.invite.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            form.addRow("邀请进服务器", self.invite)
            self.edits["token"].textChanged.connect(lambda t: self._set_invite(discord_bot.client_id_from_token(t)))
        else:
            self.invite = None
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.hide()
        outer.addWidget(self.note)
        row = QHBoxLayout()
        for text, fn in (("测试连接", self._test), ("连接", self._connect), ("断开", self._disconnect)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        outer.addLayout(row)

    def _note(self, text):
        self.note.setText(text)
        self.note.setVisible(bool(text))

    def _set_invite(self, cid):
        if self.invite is not None:
            self.invite.setText(f'<a href="{discord_bot.invite_url(cid)}">点这里邀请（只要看频道、发消息、读历史三个权限）</a>'
                                if cid else "填好 token 后自动生成")

    def load(self):
        conf = settings(self.service.app.cfg, self.platform)
        for key, e in self.edits.items():
            v = conf.get(key)
            e.setText(", ".join(map(str, v)) if isinstance(v, list) else str(v or ""))
        self.show_status(*self.service.runner.status(self.platform))

    def values(self):
        return {k: split_ids(e.text()) if k.startswith("allow_") else e.text().strip() for k, e in self.edits.items()}

    def show_status(self, state, detail):
        text = STATE_TEXT.get(state, state)
        if detail and detail not in text:
            text += f"　{detail}"
        self.state.setText(text)

    def _test(self):
        self._note("测试中…")
        self.service.check(self.platform, self.values())

    def on_checked(self, ok, text, cid):
        self._note(("✅ " if ok else "❌ ") + text)
        if ok and cid:
            self._set_invite(cid)

    def _connect(self):
        cfg = self.service.app.cfg
        conf = settings(cfg, self.platform)
        conf.update(self.values())
        if not ADAPTERS[self.platform].configured(conf):
            self._note("❌ 先把密钥填上")
            return
        conf["enabled"] = True
        save_config(cfg)
        self.service.connect_platform(self.platform)

    def _disconnect(self):
        cfg = self.service.app.cfg
        settings(cfg, self.platform)["enabled"] = False
        save_config(cfg)
        self.service.disconnect_platform(self.platform)


class IMDialog(QDialog):
    def __init__(self, service):
        super().__init__(None)
        self.service = service
        self.setWindowTitle("🔗 连接 IM")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)   # 窗口不能比内容矮，不然按钮会被压扁
        intro = QLabel(f'用你自己建的机器人，让她在 QQ / Discord 里陪大家聊天（用的是你的 DeepSeek Key）。'
                       f'她在 IM 里只能聊天和让桌面上的自己冒泡，碰不到这台电脑。'
                       f' <a href="{HELP_URL}">怎么创建机器人？</a>')
        intro.setWordWrap(True)
        intro.setOpenExternalLinks(True)
        lay.addWidget(intro)
        self.sections = {}
        self.tabs = QTabWidget()
        for p in service.platforms():
            sec = self.sections[p] = _Section(service, p)
            self.tabs.addTab(sec, ADAPTERS[p].label)
        lay.addWidget(self.tabs)
        limits = QGroupBox("回复上限（防止被刷爆 API 额度）")
        lf = QFormLayout(limits)
        self.spins = {}
        for key, label, top in (("per_user_per_min", "每人每分钟", 60), ("global_per_min", "所有人每分钟", 600),
                                ("global_per_day", "所有人每天", 100000)):
            s = QSpinBox()
            s.setRange(0, top)
            s.valueChanged.connect(self._limits_changed)
            self.spins[key] = s
            lf.addRow(label, s)
        lay.addWidget(limits)
        service.status.connect(self._on_status)
        service.checked.connect(self._on_checked)

    def load(self):
        for sec in self.sections.values():
            sec.load()
        lim = dict(DEFAULT_LIMITS, **(self.service.app.cfg.get("im", {}).get("limits") or {}))
        for k, s in self.spins.items():
            s.blockSignals(True)
            s.setValue(int(lim[k]))
            s.blockSignals(False)

    def _limits_changed(self):
        self.service.apply_limits({k: s.value() for k, s in self.spins.items()})
        save_config(self.service.app.cfg)

    def _on_status(self, platform, state, detail):
        if platform in self.sections:
            self.sections[platform].show_status(state, detail)

    def _on_checked(self, platform, ok, text, cid):
        if platform in self.sections:
            self.sections[platform].on_checked(ok, text, cid)

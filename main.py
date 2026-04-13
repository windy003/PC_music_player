import sys
import os
import random
import threading
import time
import multiprocessing
import queue

# 尝试导入Windows API用于全局快捷键
try:
    import win32api
    import win32con
    import win32gui
    import ctypes
    from ctypes import wintypes
    GLOBAL_HOTKEY_AVAILABLE = True
except ImportError:
    GLOBAL_HOTKEY_AVAILABLE = False
    print("警告: 无法导入win32api，全局快捷键功能将不可用")

from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QPushButton, QLabel, QSlider, QListWidget, 
                             QFileDialog, QMessageBox, QSystemTrayIcon, QMenu, 
                             QAction, QComboBox, QSplitter, QListWidgetItem, QShortcut,
                             QLineEdit, QInputDialog, QDialog, QFormLayout, QKeySequenceEdit,
                             QDialogButtonBox, QGroupBox)
from PyQt5.QtCore import Qt, QTimer, QUrl, pyqtSignal, QSettings, QEvent
from PyQt5.QtGui import QIcon, QPixmap, QFont, QKeySequence
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QMediaPlaylist
import pygame
import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError


# 自定义事件类
class ShowWindowEvent(QEvent):
    def __init__(self):
        super().__init__(QEvent.User + 1)


class TogglePlayEvent(QEvent):
    def __init__(self):
        super().__init__(QEvent.User + 2)


class PreviousSongEvent(QEvent):
    def __init__(self):
        super().__init__(QEvent.User + 3)


class NextSongEvent(QEvent):
    def __init__(self):
        super().__init__(QEvent.User + 4)


# 全局快捷键进程类
class GlobalHotkeyProcess:
    """独立进程的全局快捷键管理器"""
    
    def __init__(self):
        self.process = None
        self.command_queue = None
        self.event_queue = None
        self.is_running = False
        
        # 默认快捷键设置（使用 Ctrl+Alt+Shift 组合，避免冲突）
        self.hotkeys = {
            'show_window': 'Ctrl+Alt+Shift+M',
            'toggle_play': 'Ctrl+Alt+Shift+P',
            'previous_song': 'Ctrl+Alt+Shift+Left',
            'next_song': 'Ctrl+Alt+Shift+Right'
        }
    
    def start(self, hotkeys=None):
        """启动全局快捷键进程"""
        if not GLOBAL_HOTKEY_AVAILABLE:
            return False

        if self.is_running:
            return True

        if hotkeys:
            self.hotkeys.update(hotkeys)

        try:
            self.command_queue = multiprocessing.Queue()
            self.event_queue = multiprocessing.Queue()

            self.process = multiprocessing.Process(
                target=self._hotkey_process_main,
                args=(self.hotkeys, self.command_queue, self.event_queue),
                daemon=True
            )
            self.process.start()
            self.is_running = True
            return True

        except Exception:
            return False
    
    def stop(self):
        """停止全局快捷键进程"""
        if not self.is_running:
            return

        try:
            if self.command_queue:
                self.command_queue.put(('stop',))

            if self.process and self.process.is_alive():
                self.process.join(timeout=2.0)
                if self.process.is_alive():
                    self.process.terminate()
                    self.process.join()

            self.is_running = False
        except Exception:
            pass
    
    def update_hotkeys(self, hotkeys):
        """更新快捷键设置"""
        self.hotkeys.update(hotkeys)
        if self.is_running and self.command_queue:
            try:
                self.command_queue.put(('update_hotkeys', hotkeys))
            except:
                pass
    
    def get_events(self):
        """获取快捷键事件"""
        events = []
        if self.event_queue:
            try:
                while True:
                    event = self.event_queue.get_nowait()
                    events.append(event)
            except:
                pass
        return events
    
    @staticmethod
    def _hotkey_process_main(hotkeys, command_queue, event_queue):
        """全局快捷键进程主函数"""
        if not GLOBAL_HOTKEY_AVAILABLE:
            return

        # 创建消息窗口用于接收热键消息
        message_hwnd = None
        try:
            # 定义窗口类
            wc = win32gui.WNDCLASS()
            wc.lpfnWndProc = lambda hwnd, msg, wp, lp: win32gui.DefWindowProc(hwnd, msg, wp, lp)
            wc.lpszClassName = "HotkeyMessageWindow"
            wc.hInstance = win32api.GetModuleHandle(None)

            # 注册窗口类
            class_atom = win32gui.RegisterClass(wc)

            # 创建一个隐藏的真实窗口（而不是消息窗口）
            # 全局热键需要真实窗口，不能使用 HWND_MESSAGE
            message_hwnd = win32gui.CreateWindowEx(
                win32con.WS_EX_TOOLWINDOW,      # dwExStyle (工具窗口，不显示在任务栏)
                class_atom,                     # lpClassName
                "HotkeyWindow",                 # lpWindowName
                win32con.WS_POPUP,              # dwStyle (弹出窗口，无边框)
                -100, -100, 1, 1,              # x, y, width, height (屏幕外的1x1像素)
                None,                           # hWndParent
                0, wc.hInstance, None
            )
            # 确保窗口完全隐藏
            if message_hwnd:
                win32gui.ShowWindow(message_hwnd, 0)
            win32gui.PumpWaitingMessages()

        except Exception:
            pass

        if not message_hwnd:
            return

        registered_hotkeys = []
        running = True
        
        # 命名按键到 Win32 虚拟键码的映射，必须与 HotkeyLineEdit 录入的字符串保持一致
        named_keys = {
            'space':     win32con.VK_SPACE,
            'enter':     win32con.VK_RETURN,
            'return':    win32con.VK_RETURN,
            'left':      win32con.VK_LEFT,
            'right':     win32con.VK_RIGHT,
            'up':        win32con.VK_UP,
            'down':      win32con.VK_DOWN,
            'delete':    win32con.VK_DELETE,
            'del':       win32con.VK_DELETE,
            'backspace': win32con.VK_BACK,
            'tab':       win32con.VK_TAB,
            'escape':    win32con.VK_ESCAPE,
            'esc':       win32con.VK_ESCAPE,
            'home':      win32con.VK_HOME,
            'end':       win32con.VK_END,
            'pgup':      win32con.VK_PRIOR,
            'pageup':    win32con.VK_PRIOR,
            'pgdown':    win32con.VK_NEXT,
            'pagedown':  win32con.VK_NEXT,
            'ins':       win32con.VK_INSERT,
            'insert':    win32con.VK_INSERT,
        }

        def parse_hotkey(hotkey_str):
            """解析快捷键字符串"""
            if not hotkey_str:
                return None

            modifiers = 0
            key = 0

            parts = hotkey_str.split('+')
            for part in parts:
                part = part.strip().lower()
                if part == 'ctrl':
                    modifiers |= win32con.MOD_CONTROL
                elif part == 'alt':
                    modifiers |= win32con.MOD_ALT
                elif part == 'shift':
                    modifiers |= win32con.MOD_SHIFT
                elif part == 'win':
                    modifiers |= win32con.MOD_WIN
                elif len(part) == 1:
                    # A-Z, 0-9
                    key = ord(part.upper())
                elif part in named_keys:
                    key = named_keys[part]
                elif part.startswith('f') and len(part) <= 3:
                    # F1-F12
                    try:
                        f_num = int(part[1:])
                        if 1 <= f_num <= 12:
                            key = win32con.VK_F1 + f_num - 1
                    except:
                        pass

            return (modifiers, key) if key else None
        
        def register_hotkeys():
            """注册热键"""
            nonlocal registered_hotkeys

            # 先注销已注册的热键
            for hotkey_id in registered_hotkeys:
                try:
                    user32 = ctypes.windll.user32
                    user32.UnregisterHotKey(None, hotkey_id)  # 使用 NULL
                except:
                    pass
            registered_hotkeys.clear()

            # 注册新的热键
            hotkey_ids = {
                'show_window': 1,
                'toggle_play': 2,
                'previous_song': 3,
                'next_song': 4
            }

            success_count = 0
            failed_items = []  # [(action, hotkey_str, reason), ...]
            for action, hotkey_str in hotkeys.items():
                hotkey_id = hotkey_ids.get(action)
                if not hotkey_id:
                    continue

                key_code = parse_hotkey(hotkey_str)
                if not key_code:
                    failed_items.append((action, hotkey_str, "无法解析按键"))
                    continue

                try:
                    user32 = ctypes.windll.user32
                    kernel32 = ctypes.windll.kernel32
                    kernel32.SetLastError(0)

                    result = user32.RegisterHotKey(
                        None,
                        hotkey_id,
                        key_code[0],
                        key_code[1]
                    )

                    if result:
                        registered_hotkeys.append(hotkey_id)
                        success_count += 1
                    else:
                        # Windows 错误码 1409 = ERROR_HOTKEY_ALREADY_REGISTERED
                        err = kernel32.GetLastError()
                        if err == 1409:
                            reason = "已被其他程序占用"
                        else:
                            reason = f"注册失败 (错误码 {err})"
                        failed_items.append((action, hotkey_str, reason))
                except Exception as e:
                    failed_items.append((action, hotkey_str, f"异常: {e}"))

            # 通知主进程注册结果（带失败的具体明细）
            if failed_items:
                event_queue.put(('hotkey_failed', failed_items))
            return success_count > 0

        try:
            # 初始注册热键
            register_hotkeys()
            # 主消息循环
            while running:
                try:
                    # 检查命令（非阻塞）
                    try:
                        cmd = command_queue.get_nowait()
                        if cmd[0] == 'stop':
                            running = False
                            break
                        elif cmd[0] == 'update_hotkeys':
                            hotkeys.update(cmd[1])
                            register_hotkeys()
                    except:
                        pass

                    # 检查热键消息（非阻塞）
                    try:
                        # 使用 ctypes 直接调用 PeekMessageW
                        # 使用 NULL 窗口句柄获取线程消息队列中的热键消息
                        msg = wintypes.MSG()
                        result = ctypes.windll.user32.PeekMessageW(
                            ctypes.byref(msg),
                            None,  # NULL - 获取线程的所有消息
                            win32con.WM_HOTKEY,
                            win32con.WM_HOTKEY,
                            win32con.PM_REMOVE
                        )

                        if result:
                            # msg.wParam 包含 hotkey_id
                            hotkey_id = msg.wParam
                            if hotkey_id == 1:
                                event_queue.put('show_window')
                            elif hotkey_id == 2:
                                event_queue.put('toggle_play')
                            elif hotkey_id == 3:
                                event_queue.put('previous_song')
                            elif hotkey_id == 4:
                                event_queue.put('next_song')
                    except Exception:
                        pass

                    time.sleep(0.01)

                except Exception:
                    break

        except Exception:
            pass
        
        finally:
            # 清理注册的热键
            for hotkey_id in registered_hotkeys:
                try:
                    ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)
                except:
                    pass

            # 销毁消息窗口
            if message_hwnd:
                try:
                    win32gui.DestroyWindow(message_hwnd)
                except:
                    pass

            try:
                win32gui.UnregisterClass("HotkeyMessageWindow", win32api.GetModuleHandle(None))
            except:
                pass


# 自定义按键捕获输入框
class HotkeyLineEdit(QLineEdit):
    def __init__(self, parent=None, allow_no_modifiers=False):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("点击此处并按下快捷键...")
        self.current_keys = []
        # 是否允许无修饰键的快捷键（本地快捷键允许，全局快捷键通常需要修饰键）
        self.allow_no_modifiers = allow_no_modifiers

    def keyPressEvent(self, event):
        # 记录按下的键
        modifiers = []
        if event.modifiers() & Qt.ControlModifier:
            modifiers.append("Ctrl")
        if event.modifiers() & Qt.AltModifier:
            modifiers.append("Alt")
        if event.modifiers() & Qt.ShiftModifier:
            modifiers.append("Shift")
        if event.modifiers() & Qt.MetaModifier:
            modifiers.append("Win")

        # 获取主键
        key_text = ""
        key = event.key()

        if Qt.Key_A <= key <= Qt.Key_Z:
            key_text = chr(key)
        elif Qt.Key_0 <= key <= Qt.Key_9:
            key_text = chr(key)
        elif key == Qt.Key_Space:
            key_text = "Space"
        elif key == Qt.Key_Return or key == Qt.Key_Enter:
            key_text = "Enter"
        elif key == Qt.Key_Left:
            key_text = "Left"
        elif key == Qt.Key_Right:
            key_text = "Right"
        elif key == Qt.Key_Up:
            key_text = "Up"
        elif key == Qt.Key_Down:
            key_text = "Down"
        elif key == Qt.Key_Delete:
            key_text = "Delete"
        elif key == Qt.Key_Backspace:
            key_text = "Backspace"
        elif key == Qt.Key_Tab:
            key_text = "Tab"
        elif key == Qt.Key_Escape:
            key_text = "Escape"
        elif key == Qt.Key_Home:
            key_text = "Home"
        elif key == Qt.Key_End:
            key_text = "End"
        elif key == Qt.Key_PageUp:
            key_text = "PgUp"
        elif key == Qt.Key_PageDown:
            key_text = "PgDown"
        elif key == Qt.Key_Insert:
            key_text = "Ins"
        elif Qt.Key_F1 <= key <= Qt.Key_F12:
            key_text = "F" + str(key - Qt.Key_F1 + 1)

        # 如果有有效的主键，组合快捷键字符串
        if key_text:
            if modifiers:
                hotkey_str = "+".join(modifiers + [key_text])
                self.setText(hotkey_str)
            elif self.allow_no_modifiers:
                self.setText(key_text)

        # 不调用父类的keyPressEvent，防止默认处理


# 自定义搜索框，支持方向键导航
class SearchLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        
    def keyPressEvent(self, event):
        # 如果按下下方向键，聚焦到播放列表
        if event.key() == Qt.Key_Down:
            if self.parent_window and hasattr(self.parent_window, 'playlist_widget'):
                self.parent_window.focus_playlist_from_search()
            return
        
        # 其他按键正常处理
        super().keyPressEvent(event)


# 自定义播放列表，支持回车键播放
class PlaylistWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        
    def keyPressEvent(self, event):
        # 如果按下回车键，播放选中的歌曲
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            current_item = self.currentItem()
            if current_item and self.parent_window:
                self.parent_window.play_selected_song(current_item)
            return
        
        # 其他按键正常处理
        super().keyPressEvent(event)


class ShortcutSettingsDialog(QDialog):
    """统一的快捷键设置对话框，包含本地快捷键和全局快捷键两个分页"""

    def __init__(self, local_definitions, current_local_values,
                 global_definitions=None, current_global_values=None, parent=None):
        """
        :param local_definitions: list of (key, label, default, callback_name)
        :param current_local_values: dict {key: hotkey_str}
        :param global_definitions: list of (key, label, default) 或 None
        :param current_global_values: dict {key: hotkey_str} 或 None
        """
        super().__init__(parent)
        self.setWindowTitle("快捷键设置")
        self.setModal(True)
        self.resize(520, 640)

        if parent:
            self.setWindowIcon(parent.windowIcon())

        self.local_definitions = local_definitions
        self.global_definitions = global_definitions or []
        self.local_edits = {}   # key -> HotkeyLineEdit
        self.global_edits = {}  # key -> HotkeyLineEdit

        # key -> 显示标签，用于在错误提示里指出具体是哪个动作冲突
        self.local_labels = {key: label for key, label, _, _ in local_definitions}
        self.global_labels = {key: label for key, label, _ in self.global_definitions}

        from PyQt5.QtWidgets import QScrollArea, QTabWidget

        layout = QVBoxLayout()

        tab_widget = QTabWidget()

        # ========== 本地快捷键页 ==========
        local_page = QWidget()
        local_page_layout = QVBoxLayout()
        local_page.setLayout(local_page_layout)

        local_info = QLabel("仅在程序窗口聚焦时生效。")
        local_info.setStyleSheet("color: gray; font-size: 11px; margin-bottom: 4px;")
        local_page_layout.addWidget(local_info)

        local_scroll = QScrollArea()
        local_scroll.setWidgetResizable(True)
        local_form_container = QWidget()
        local_form_layout = QFormLayout()
        local_form_container.setLayout(local_form_layout)

        for key, label, default, _callback in local_definitions:
            edit = HotkeyLineEdit(allow_no_modifiers=True)
            edit.setText(current_local_values.get(key, default))
            self.local_edits[key] = edit
            local_form_layout.addRow(label + ":", edit)

        local_scroll.setWidget(local_form_container)
        local_page_layout.addWidget(local_scroll)

        tab_widget.addTab(local_page, "本地快捷键")

        # ========== 全局快捷键页 ==========
        if self.global_definitions:
            global_page = QWidget()
            global_page_layout = QVBoxLayout()
            global_page.setLayout(global_page_layout)

            global_info = QLabel("程序在后台运行时也可使用，建议使用 Ctrl+Alt+Shift 三键组合避免冲突。")
            global_info.setStyleSheet("color: gray; font-size: 11px; margin-bottom: 4px;")
            global_info.setWordWrap(True)
            global_page_layout.addWidget(global_info)

            global_form_layout = QFormLayout()
            for key, label, default in self.global_definitions:
                edit = HotkeyLineEdit(allow_no_modifiers=False)
                edit.setText((current_global_values or {}).get(key, default))
                self.global_edits[key] = edit
                global_form_layout.addRow(label + ":", edit)

            global_page_layout.addLayout(global_form_layout)
            global_page_layout.addStretch()

            tab_widget.addTab(global_page, "全局快捷键")

        layout.addWidget(tab_widget)

        # 帮助说明
        help_label = QLabel(
            "使用方法: 点击输入框，按下想要设置的快捷键。\n"
            "本地快捷键支持单键，全局快捷键必须包含 Ctrl/Alt/Shift/Win 等修饰键。"
        )
        help_label.setStyleSheet("color: gray; font-size: 10px;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def _validate(self, edits, labels, group_name):
        """校验单组（本地或全局）：不能为空，不能重复。
        发现冲突时一次性列出所有冲突的快捷键和对应动作。"""
        values = {key: edit.text().strip() for key, edit in edits.items()}

        # 校验：未设置的项
        empty_keys = [key for key, v in values.items() if not v]
        if empty_keys:
            empty_labels = [labels.get(k, k) for k in empty_keys]
            QMessageBox.warning(
                self, "输入错误",
                f"{group_name}中以下项未设置快捷键：\n  • " + "\n  • ".join(empty_labels)
            )
            return None

        # 统计每个快捷键被哪些动作使用
        by_value = {}
        for key, v in values.items():
            by_value.setdefault(v, []).append(key)

        # 找出所有冲突组（同一快捷键被 ≥2 个动作使用）
        conflicts = [(v, keys) for v, keys in by_value.items() if len(keys) > 1]
        if conflicts:
            lines = [f"{group_name}中存在以下快捷键冲突：\n"]
            for v, keys in conflicts:
                action_labels = "、".join(labels.get(k, k) for k in keys)
                lines.append(f'  • "{v}"  →  {action_labels}')
            lines.append("\n请修改后再保存。")
            QMessageBox.warning(self, "快捷键冲突", "\n".join(lines))
            return None

        return values

    def accept(self):
        local_values = self._validate(self.local_edits, self.local_labels, "本地快捷键")
        if local_values is None:
            return

        global_values = None
        if self.global_edits:
            global_values = self._validate(self.global_edits, self.global_labels, "全局快捷键")
            if global_values is None:
                return

        self.local_values = local_values
        self.global_values = global_values
        super().accept()


class MusicPlayer(QMainWindow):
    def get_resource_path(self, relative_path):
        """获取资源文件路径，支持PyInstaller打包"""
        try:
            # PyInstaller创建临时文件夹，将路径存储在_MEIPASS中
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("音乐播放器:2025/07/23-02")

        # 设置应用图标
        icon_path = self.get_resource_path("1024x1024.png")
        self.app_icon = QIcon(icon_path)
        self.setWindowIcon(self.app_icon)

        # Windows 特定：设置任务栏图标
        if sys.platform == 'win32':
            try:
                import ctypes
                # 设置应用程序 ID，确保任务栏图标正确显示
                myappid = 'mycompany.musicplayer.version1'
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except:
                pass

        # 设置窗口初始大小（用于非最大化状态）
        self.setGeometry(100, 100, 800, 600)

        # 初始化 pygame 音频
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        except Exception:
            try:
                pygame.mixer.init()
            except Exception:
                pass

        # 播放状态
        self.is_playing = False
        self.current_position = 0
        self.duration = 0
        self.volume = 70
        self.current_index = -1  # 当前播放的歌曲索引
        self.music_loaded = False  # 标记是否已加载音乐文件
        self.seek_offset = 0  # 跳转偏移量，用于修正 pygame.mixer.music.get_pos()

        # 设置初始音量 (pygame 音量范围 0.0-1.0)
        pygame.mixer.music.set_volume(self.volume / 100.0)
        
        # 播放模式 0:顺序播放 1:单曲循环 2:随机播放
        self.play_mode = 0
        
        # 单曲循环模式下的用户操作标记
        self.user_manual_skip = False
        
        # 歌曲信息列表
        self.song_list = []
        
        # 播放历史记录（用于上一曲功能）
        self.play_history = []
        self.history_index = -1
        
        # 初始化设置
        self.settings = QSettings("MusicPlayer", "PlaylistMemory")
        
        # 全局快捷键进程管理器
        self.global_hotkey_process = None
        self.hotkey_failed_shown = False  # 防止重复弹出对话框
        if GLOBAL_HOTKEY_AVAILABLE:
            self.global_hotkey_process = GlobalHotkeyProcess()
            
            # 从设置中加载快捷键（默认使用 Ctrl+Alt+Shift 避免冲突）
            old_show_key = self.settings.value("global_show_key", "", type=str)
            if old_show_key and not old_show_key.startswith("Ctrl+Alt+Shift"):
                self.settings.remove("global_show_key")
                self.settings.remove("global_play_key")
                self.settings.remove("global_prev_key")
                self.settings.remove("global_next_key")

            hotkeys = {
                'show_window': self.settings.value("global_show_key", "Ctrl+Alt+Shift+M", type=str),
                'toggle_play': self.settings.value("global_play_key", "Ctrl+Alt+Shift+P", type=str),
                'previous_song': self.settings.value("global_prev_key", "Ctrl+Alt+Shift+Left", type=str),
                'next_song': self.settings.value("global_next_key", "Ctrl+Alt+Shift+Right", type=str)
            }
            self.global_hotkey_process.hotkeys = hotkeys
        
        # 初始化UI
        self.init_ui()
        
        # 初始化系统托盘
        self.init_tray()
        
        # 初始化快捷键
        self.init_shortcuts()
        
        # 连接信号
        self.connect_signals()
        
        # 定时器更新进度 - 减少更新频率以优化蓝牙播放
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(1000)  # 保持1秒更新一次进度条
        
        # 音频状态监控定时器（已禁用，因为会导致播放循环问题）
        # self.audio_monitor_timer = QTimer()
        # self.audio_monitor_timer.timeout.connect(self.monitor_audio_status)
        # self.audio_monitor_timer.start(1000)
        
        # 加载上次的播放列表
        self.load_last_playlist()
        
        # 延迟初始化全局快捷键进程（避免与窗口初始化冲突）
        if self.global_hotkey_process:
            QTimer.singleShot(500, self.start_global_hotkey_process)

        # 设置窗口最大化（在所有初始化完成后）
        self.setWindowState(Qt.WindowMaximized)

    def start_global_hotkey_process(self):
        """延迟启动全局快捷键进程"""
        if self.global_hotkey_process:
            self.global_hotkey_process.start()
            # 启动事件监听定时器
            self.hotkey_event_timer = QTimer()
            self.hotkey_event_timer.timeout.connect(self.check_hotkey_events)
            self.hotkey_event_timer.start(50)  # 每50ms检查一次事件

    def event(self, event):
        """处理自定义事件"""
        if event.type() == QEvent.User + 1:  # ShowWindowEvent
            self.show_window()
            return True
        elif event.type() == QEvent.User + 2:  # TogglePlayEvent
            self.toggle_play()
            return True
        elif event.type() == QEvent.User + 3:  # PreviousSongEvent
            self.previous_song()
            return True
        elif event.type() == QEvent.User + 4:  # NextSongEvent
            self.next_song()
            return True
        return super().event(event)
    
    def check_hotkey_events(self):
        """检查全局快捷键事件"""
        if not self.global_hotkey_process:
            return

        try:
            events = self.global_hotkey_process.get_events()
        except Exception as e:
            return

        for event in events:
            # 处理元组事件（如热键注册失败通知）
            if isinstance(event, tuple):
                if event[0] == 'hotkey_failed':
                    # 兼容旧格式（数字）和新格式（明细列表）
                    payload = event[1] if len(event) > 1 else None
                    failed_items = payload if isinstance(payload, list) else None
                    QTimer.singleShot(
                        500,
                        lambda items=failed_items: self.show_hotkey_failed_dialog(items)
                    )
            elif event == 'show_window':
                self.show_window()
            elif event == 'toggle_play':
                self.toggle_play()
            elif event == 'previous_song':
                self.previous_song()
            elif event == 'next_song':
                self.next_song()

    def show_hotkey_failed_dialog(self, failed_items=None):
        """显示热键注册失败对话框，列出具体被占用的快捷键。
        :param failed_items: list of (action_key, hotkey_str, reason)
        """
        # 防止重复弹出
        if self.hotkey_failed_shown:
            return
        self.hotkey_failed_shown = True

        # 把内部 action key 翻译为中文标签
        label_map = {key: label for key, label, _ in self.GLOBAL_HOTKEY_DEFINITIONS}

        if failed_items:
            lines = ["以下全局快捷键注册失败：\n"]
            for action_key, hotkey_str, reason in failed_items:
                label = label_map.get(action_key, action_key)
                lines.append(f'  • {label}：{hotkey_str}   ({reason})')
            lines.append("\n是否打开快捷键设置来自定义新的快捷键组合？")
            lines.append("\n提示：建议使用 Ctrl+Shift 或 Ctrl+Alt+Shift 组合避免冲突")
            text = "\n".join(lines)
        else:
            text = (
                "部分或全部全局快捷键被其他程序占用。\n\n"
                "是否打开快捷键设置来自定义新的快捷键组合？\n\n"
                "提示：建议使用 Ctrl+Shift 或 Ctrl+Alt+Shift 组合"
            )

        reply = QMessageBox.warning(
            self,
            "全局快捷键注册失败",
            text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self.show_shortcut_settings()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # 顶部按钮区域
        top_layout = QHBoxLayout()
        
        # 打开文件按钮
        self.open_file_btn = QPushButton("打开文件 (Alt+O)")
        self.open_file_btn.clicked.connect(self.open_file)
        top_layout.addWidget(self.open_file_btn)
        
        # 打开文件夹按钮
        self.open_folder_btn = QPushButton("打开文件夹 (Alt+F)")
        self.open_folder_btn.clicked.connect(self.open_folder)
        top_layout.addWidget(self.open_folder_btn)

        # 清空播放列表按钮
        self.clear_all_btn = QPushButton("清空列表")
        self.clear_all_btn.clicked.connect(self.clear_playlist_and_settings)
        self.clear_all_btn.setToolTip("清空播放列表并删除保存的记录")
        top_layout.addWidget(self.clear_all_btn)

        # 播放模式选择
        mode_label = QLabel("播放模式 (Alt+M/L):")
        top_layout.addWidget(mode_label)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["顺序播放", "智能单曲循环", "随机播放"])
        self.mode_combo.currentIndexChanged.connect(self.change_play_mode)
        self.mode_combo.setToolTip("播放模式: Alt+M(循环切换) Alt+L(打开下拉菜单)\n智能单曲循环: 自然播放结束时循环，手动切换时随机跳转")
        top_layout.addWidget(self.mode_combo)
        
        # 快捷键设置按钮（包含本地和全局两个分页）
        self.shortcut_btn = QPushButton("快捷键设置")
        self.shortcut_btn.clicked.connect(self.show_shortcut_settings)
        self.shortcut_btn.setToolTip("自定义本地快捷键（窗口聚焦时生效）和全局快捷键（后台也生效）")
        top_layout.addWidget(self.shortcut_btn)
        
        # 音频设备选择按钮
        self.audio_device_btn = QPushButton("音频设备设置")
        self.audio_device_btn.clicked.connect(self.show_audio_device_settings)
        self.audio_device_btn.setToolTip("选择音频输出设备，可能帮助解决蓝牙耳机播放问题")
        top_layout.addWidget(self.audio_device_btn)
        
        top_layout.addStretch()
        main_layout.addLayout(top_layout)
        
        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # 左侧播放列表区域
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_widget.setLayout(left_layout)
        
        # 搜索框
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索 (Alt+D):"))
        self.search_box = SearchLineEdit(self) # Pass self as parent
        self.search_box.setPlaceholderText("输入歌曲名称或艺术家...")
        self.search_box.textChanged.connect(self.filter_playlist)
        search_layout.addWidget(self.search_box)
        
        # 定位按钮
        locate_btn = QPushButton("定位 (Alt+G)")
        locate_btn.clicked.connect(self.locate_current_song)
        locate_btn.setToolTip("定位到正在播放的歌曲")
        search_layout.addWidget(locate_btn)
        
        # 清除搜索按钮
        clear_search_btn = QPushButton("清除 (Alt+C)")
        clear_search_btn.clicked.connect(self.clear_search)
        search_layout.addWidget(clear_search_btn)
        
        left_layout.addLayout(search_layout)

        # 当前文件夹标签
        self.folder_label = QLabel("")
        self.folder_label.setStyleSheet("color: #4a90d9; font-size: 18px; padding: 2px 4px;")
        self.folder_label.setAlignment(Qt.AlignLeft)
        self.folder_label.setVisible(False)
        left_layout.addWidget(self.folder_label)

        # 播放列表
        self.playlist_widget = PlaylistWidget(self) # Pass self as parent
        self.playlist_widget.itemDoubleClicked.connect(self.play_selected_song)
        self.playlist_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.playlist_widget.customContextMenuRequested.connect(self.show_context_menu)
        left_layout.addWidget(self.playlist_widget)
        
        # 播放列表快捷键提示
        playlist_hint_label = QLabel("提示: ↓(从搜索框进入) Enter(播放) Alt+G(定位正在播放) Ctrl+R(重命名) Delete(删除) 双击播放")
        playlist_hint_label.setStyleSheet("color: gray; font-size: 10px;")
        playlist_hint_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(playlist_hint_label)
        
        splitter.addWidget(left_widget)
        
        # 右侧控制区域
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_widget.setLayout(right_layout)
        
        # 当前播放信息
        self.current_song_label = QLabel("没有正在播放的歌曲")
        self.current_song_label.setAlignment(Qt.AlignCenter)
        self.current_song_label.setFont(QFont("Arial", 12, QFont.Bold))
        right_layout.addWidget(self.current_song_label)
        
        # 进度条
        progress_layout = QHBoxLayout()
        self.time_label = QLabel("00:00")
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.sliderPressed.connect(self.slider_pressed)
        self.progress_slider.sliderReleased.connect(self.slider_released)
        self.progress_slider.setToolTip("进度条 (←后退5秒, →前进5秒)")
        self.total_time_label = QLabel("00:00")
        
        progress_layout.addWidget(self.time_label)
        progress_layout.addWidget(self.progress_slider)
        progress_layout.addWidget(self.total_time_label)
        right_layout.addLayout(progress_layout)
        
        # 方向键提示
        seek_hint_label = QLabel("提示: ←后退5秒 / →前进5秒")
        seek_hint_label.setStyleSheet("color: gray; font-size: 10px;")
        seek_hint_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(seek_hint_label)
        
        # 控制按钮
        control_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("上一曲 (Alt+←)")
        self.prev_btn.clicked.connect(self.previous_song)
        control_layout.addWidget(self.prev_btn)
        
        self.play_btn = QPushButton("播放 (Alt+P/空格)")
        self.play_btn.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_btn)
        
        self.next_btn = QPushButton("下一曲 (Alt+→)")
        self.next_btn.clicked.connect(self.next_song)
        self.next_btn.setToolTip("下一曲 (Alt+→)\n智能单曲循环模式: Alt+→ 随机下一曲")
        control_layout.addWidget(self.next_btn)
        
        right_layout.addLayout(control_layout)
        
        # 音量控制
        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("音量 (Alt+↑/↓):"))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.volume)
        self.volume_slider.valueChanged.connect(self.change_volume)
        self.volume_slider.setToolTip("音量调节 (Alt+↑增加, Alt+↓减少)")
        volume_layout.addWidget(self.volume_slider)
        self.volume_label = QLabel(f"{self.volume}%")
        volume_layout.addWidget(self.volume_label)
        right_layout.addLayout(volume_layout)
        
        right_layout.addStretch()
        splitter.addWidget(right_widget)
        
        # 设置分割器比例
        splitter.setSizes([400, 400])

    def init_tray(self):
        """初始化系统托盘"""
        try:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                self.tray_icon = None
                return

            self.tray_icon = QSystemTrayIcon(self)
            icon_path = self.get_resource_path("1024x1024.png")
            self.tray_icon.setIcon(QIcon(icon_path))

            tray_menu = QMenu()

            show_action = QAction("显示", self)
            show_action.triggered.connect(self.show_window)
            tray_menu.addAction(show_action)

            play_action = QAction("播放/暂停", self)
            play_action.triggered.connect(self.toggle_play)
            tray_menu.addAction(play_action)

            next_action = QAction("下一曲", self)
            next_action.triggered.connect(self.next_song)
            tray_menu.addAction(next_action)

            tray_menu.addSeparator()

            quit_action = QAction("退出 (&X)", self)
            quit_action.triggered.connect(self.quit_application)
            tray_menu.addAction(quit_action)

            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self.tray_icon_activated)
            self.tray_icon.show()
        except Exception:
            self.tray_icon = None

    # 本地快捷键定义表：(key, 显示标签, 默认快捷键, 回调方法名)
    # 修改默认值或新增条目时只需改这里
    LOCAL_SHORTCUT_DEFINITIONS = [
        ("open_file",         "打开文件",           "Alt+O",     "open_file"),
        ("open_folder",       "打开文件夹",         "Alt+F",     "open_folder"),
        ("toggle_play",       "播放/暂停",         "Alt+P",     "toggle_play"),
        ("previous_song",     "上一曲",            "Alt+Left",  "previous_song"),
        ("next_song",         "下一曲(智能)",      "Alt+Right", "smart_next_shortcut"),
        ("cycle_play_mode",   "切换播放模式",       "Alt+M",     "cycle_play_mode"),
        ("show_mode_dropdown","展开播放模式下拉",   "Alt+L",     "show_mode_dropdown"),
        ("volume_up",         "音量增加",           "Alt+Up",    "volume_up"),
        ("volume_down",       "音量减少",           "Alt+Down",  "volume_down"),
        ("toggle_play_space", "播放/暂停(空格)",   "Space",     "toggle_play"),
        ("seek_backward",     "后退5秒",           "Left",      "seek_backward"),
        ("seek_forward",      "前进5秒",           "Right",     "seek_forward"),
        ("focus_search",      "聚焦搜索框",         "Alt+D",     "focus_search_box"),
        ("clear_search",      "清除搜索",           "Alt+C",     "clear_search"),
        ("locate_current",    "定位当前歌曲",       "Alt+G",     "locate_current_song"),
        ("rename",            "重命名选中项",       "Ctrl+R",    "rename_current_item"),
        ("delete",            "删除选中项",         "Delete",    "delete_current_item"),
    ]

    # 全局快捷键定义表：(key, 显示标签, 默认快捷键)
    GLOBAL_HOTKEY_DEFINITIONS = [
        ("show_window",   "显示窗口",  "Ctrl+Alt+Shift+M"),
        ("toggle_play",   "播放/暂停", "Ctrl+Alt+Shift+P"),
        ("previous_song", "上一曲",    "Ctrl+Alt+Shift+Left"),
        ("next_song",     "下一曲",    "Ctrl+Alt+Shift+Right"),
    ]

    # 全局快捷键 key 到 QSettings 字段名的映射
    GLOBAL_HOTKEY_SETTINGS_KEYS = {
        "show_window":   "global_show_key",
        "toggle_play":   "global_play_key",
        "previous_song": "global_prev_key",
        "next_song":     "global_next_key",
    }

    def _load_local_shortcut_values(self):
        """从 QSettings 读取本地快捷键设置，没有则用默认值"""
        values = {}
        for key, _label, default, _callback in self.LOCAL_SHORTCUT_DEFINITIONS:
            values[key] = self.settings.value(f"local_shortcut_{key}", default, type=str)
        return values

    def init_shortcuts(self):
        """初始化本地快捷键（基于定义表 + QSettings）"""
        # 存放所有 QShortcut 对象，便于后续修改
        self.local_shortcuts = {}
        values = self._load_local_shortcut_values()

        for key, _label, _default, callback_name in self.LOCAL_SHORTCUT_DEFINITIONS:
            hotkey_str = values[key]
            shortcut = QShortcut(QKeySequence(hotkey_str), self)
            callback = getattr(self, callback_name, None)
            if callback:
                shortcut.activated.connect(callback)
            self.local_shortcuts[key] = shortcut

    def apply_local_shortcuts(self, values):
        """根据新值更新所有本地快捷键的按键序列"""
        for key, _label, _default, _callback in self.LOCAL_SHORTCUT_DEFINITIONS:
            shortcut = self.local_shortcuts.get(key)
            if shortcut and key in values:
                shortcut.setKey(QKeySequence(values[key]))

    def show_shortcut_settings(self):
        """显示统一的快捷键设置对话框（包含本地和全局两个分页）"""
        current_local_values = {
            key: self.local_shortcuts[key].key().toString()
            for key, _l, _d, _c in self.LOCAL_SHORTCUT_DEFINITIONS
        }

        # 全局快捷键（如果可用）
        global_definitions = None
        current_global_values = None
        if self.global_hotkey_process:
            global_definitions = self.GLOBAL_HOTKEY_DEFINITIONS
            current_global_values = dict(self.global_hotkey_process.hotkeys)

        dialog = ShortcutSettingsDialog(
            self.LOCAL_SHORTCUT_DEFINITIONS, current_local_values,
            global_definitions, current_global_values, self
        )

        if dialog.exec_() == QDialog.Accepted:
            # 应用并持久化本地快捷键
            self.apply_local_shortcuts(dialog.local_values)
            for key, v in dialog.local_values.items():
                self.settings.setValue(f"local_shortcut_{key}", v)

            # 应用并持久化全局快捷键
            if dialog.global_values is not None and self.global_hotkey_process:
                self.global_hotkey_process.update_hotkeys(dialog.global_values)
                for key, v in dialog.global_values.items():
                    settings_key = self.GLOBAL_HOTKEY_SETTINGS_KEYS.get(key)
                    if settings_key:
                        self.settings.setValue(settings_key, v)
                # 重置失败提示标记，以便下次注册失败时仍可弹窗
                self.hotkey_failed_shown = False

            QMessageBox.information(self, "设置成功", "快捷键已更新。")

    def connect_signals(self):
        """连接信号和槽"""
        # 已改用 pygame，不再使用 QMediaPlayer 的信号
        pass

    def open_file(self):
        """打开音频文件"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择音频文件", "", 
            "音频文件 (*.mp3 *.wav *.m4a *.flac *.ogg);;所有文件 (*)"
        )
        
        if file_paths:
            # 清空旧的播放列表
            self.clear_playlist()
            self.add_files_to_playlist(file_paths)
            # 保存播放列表
            self.save_playlist()

    def open_folder(self):
        """打开文件夹"""
        folder_path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        
        if folder_path:
            audio_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.ogg']
            file_paths = []

            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in audio_extensions):
                        file_paths.append(os.path.join(root, file))

            if file_paths:
                # 清空旧的播放列表
                self.clear_playlist()
                self.add_files_to_playlist(file_paths)
                # 显示文件夹名
                folder_name = os.path.basename(folder_path)
                self.folder_label.setText(f"文件夹: {folder_name}")
                self.folder_label.setVisible(True)
                # 保存播放列表
                self.save_playlist()
            else:
                QMessageBox.information(self, "提示", "所选文件夹中没有找到音频文件")

    def clear_playlist(self):
        """清空播放列表"""
        # 停止播放
        pygame.mixer.music.stop()

        # 清空所有播放列表相关数据
        self.song_list.clear()
        self.playlist_widget.clear()
        self.play_history.clear()

        # 重置播放状态
        self.current_position = 0
        self.seek_offset = 0
        self.duration = 0
        self.is_playing = False
        self.current_index = -1
        self.music_loaded = False

        # 更新UI显示
        self.current_song_label.setText("没有正在播放的歌曲")
        self.progress_slider.setValue(0)
        self.time_label.setText("00:00")
        self.total_time_label.setText("00:00")
        self.play_btn.setText("播放 (Alt+P/空格)")
        self.folder_label.setText("")
        self.folder_label.setVisible(False)

    def clear_playlist_and_settings(self):
        """清空播放列表并删除保存的设置"""
        # 清空当前播放列表
        self.clear_playlist()

        # 删除保存的播放列表设置
        self.settings.remove("playlist_full")
        self.settings.remove("playlist")
        self.settings.remove("current_index")
        self.settings.remove("folder_label")


    def add_files_to_playlist(self, file_paths):
        """添加文件到播放列表"""
        for file_path in file_paths:
            # 规范化路径
            file_path = os.path.normpath(file_path)

            # 获取歌曲信息
            song_info = self.get_song_info(file_path)
            self.song_list.append(song_info)

            # 添加到UI列表
            display_text = song_info.get('display_name', f"{song_info['title']} - {song_info['artist']}")
            item = QListWidgetItem(display_text)
            self.playlist_widget.addItem(item)


    def get_song_info(self, file_path):
        """获取歌曲信息"""
        song_info = {
            'path': file_path,
            'title': os.path.basename(file_path),
            'artist': '未知艺术家',
            'album': '未知专辑',
            'duration': 0
        }
        
        try:
            audio_file = mutagen.File(file_path)
            if audio_file is not None:
                # 获取标题
                if 'TIT2' in audio_file:
                    song_info['title'] = str(audio_file['TIT2'])
                elif 'TITLE' in audio_file:
                    song_info['title'] = str(audio_file['TITLE'][0])
                
                # 获取艺术家
                if 'TPE1' in audio_file:
                    song_info['artist'] = str(audio_file['TPE1'])
                elif 'ARTIST' in audio_file:
                    song_info['artist'] = str(audio_file['ARTIST'][0])
                
                # 获取专辑
                if 'TALB' in audio_file:
                    song_info['album'] = str(audio_file['TALB'])
                elif 'ALBUM' in audio_file:
                    song_info['album'] = str(audio_file['ALBUM'][0])
                
                # 获取时长
                if hasattr(audio_file, 'info') and hasattr(audio_file.info, 'length'):
                    song_info['duration'] = int(audio_file.info.length)
        except Exception:
            pass
        
        return song_info

    def play_selected_song(self, item):
        """播放选中的歌曲"""
        index = self.playlist_widget.row(item)
        self.play_song_at_index(index)
        # 重置手动跳转标记
        self.user_manual_skip = False
        # 记录到播放历史
        self.add_to_history(index)

    def play_song_at_index(self, index):
        """播放指定索引的歌曲"""
        if 0 <= index < len(self.song_list):
            song_info = self.song_list[index]
            file_path = song_info['path']
            try:
                pygame.mixer.music.load(file_path)
                self.music_loaded = True
                pygame.mixer.music.play()
                self.current_index = index
                self.is_playing = True
                self.current_position = 0
                self.seek_offset = 0  # 重置跳转偏移量
                self.duration = song_info.get('duration', 0) * 1000
                self.update_current_song_display()
                self.play_btn.setText("暂停 (Alt+P/空格)")
            except Exception as e:
                print(f"播放失败: {e}")

    def toggle_play(self):
        """切换播放/暂停"""
        try:
            if self.is_playing:
                pygame.mixer.music.pause()
                self.is_playing = False
                self.play_btn.setText("播放 (Alt+P/空格)")
            else:
                # 如果音乐已加载，恢复播放
                if self.music_loaded and self.current_index >= 0:
                    pygame.mixer.music.unpause()
                    self.is_playing = True
                    self.play_btn.setText("暂停 (Alt+P/空格)")
                # 如果音乐未加载但有歌曲列表，播放当前索引或第一首
                elif len(self.song_list) > 0:
                    play_index = self.current_index if self.current_index >= 0 else 0
                    self.play_song_at_index(play_index)
        except Exception as e:
            print(f"toggle_play 错误: {e}")

    def previous_song(self):
        """上一曲 - 从历史记录中获取上一曲"""
        # 尝试从历史记录获取上一曲
        prev_index = self.get_previous_from_history()
        if prev_index is not None:
            self.play_song_at_index(prev_index)
        else:
            # 如果没有历史记录，随机播放一首歌
            if len(self.song_list) > 0:
                random_index = random.randint(0, len(self.song_list) - 1)
                # 避免选择相同的歌曲
                while random_index == self.current_index and len(self.song_list) > 1:
                    random_index = random.randint(0, len(self.song_list) - 1)
                self.play_song_at_index(random_index)

    def next_song(self):
        """下一曲 - 随机播放下一曲"""
        if len(self.song_list) > 0:
            # 记录当前播放的歌曲到历史记录
            if self.current_index >= 0:
                self.add_to_history(self.current_index)

            # 随机选择下一曲
            random_index = random.randint(0, len(self.song_list) - 1)
            # 避免选择相同的歌曲（如果列表中有多首歌）
            while random_index == self.current_index and len(self.song_list) > 1:
                random_index = random.randint(0, len(self.song_list) - 1)

            self.play_song_at_index(random_index)

    def play_random_song(self):
        """播放随机歌曲"""
        if len(self.song_list) > 0:
            random_index = random.randint(0, len(self.song_list) - 1)
            self.play_song_at_index(random_index)
            self.add_to_history(random_index)

    def change_play_mode(self, index):
        """改变播放模式"""
        self.play_mode = index
        if index == 1:  # 单曲循环（智能模式）
            self.user_manual_skip = False  # 重置手动跳转标记

        # 保存播放模式
        self.settings.setValue("play_mode", self.play_mode)

    def change_volume(self, value):
        """改变音量"""
        self.volume = value
        pygame.mixer.music.set_volume(value / 100.0)
        self.volume_label.setText(f"{value}%")

        # 保存音量设置
        self.settings.setValue("volume", self.volume)

    def update_current_song_display(self):
        """更新当前歌曲显示"""
        if 0 <= self.current_index < len(self.song_list):
            song_info = self.song_list[self.current_index]
            display_text = song_info.get('display_name', f"{song_info['title']} - {song_info['artist']}")
            self.current_song_label.setText(display_text)

            # 高亮当前播放的歌曲
            for i in range(self.playlist_widget.count()):
                item = self.playlist_widget.item(i)
                if i == self.current_index:
                    item.setBackground(Qt.lightGray)
                else:
                    item.setBackground(Qt.white)

            # 更新进度条范围
            self.progress_slider.setRange(0, self.duration)
            self.total_time_label.setText(self.format_time(self.duration))

            # 保存当前播放位置
            self.settings.setValue("current_index", self.current_index)

    def cycle_play_mode(self):
        """循环切换播放模式"""
        current_mode = self.mode_combo.currentIndex()
        next_mode = (current_mode + 1) % 3
        self.mode_combo.setCurrentIndex(next_mode)
        # 重置手动跳转标记
        self.user_manual_skip = False

    def show_mode_dropdown(self):
        """显示播放模式下拉菜单"""
        self.mode_combo.showPopup()

    def volume_up(self):
        """音量增加"""
        current_volume = self.volume_slider.value()
        new_volume = min(100, current_volume + 10)
        self.volume_slider.setValue(new_volume)

    def volume_down(self):
        """音量减少"""
        current_volume = self.volume_slider.value()
        new_volume = max(0, current_volume - 10)
        self.volume_slider.setValue(new_volume)

    def seek_backward(self):
        """后退5秒"""
        if self.is_playing and self.current_index >= 0:
            # pygame 不支持直接 seek，需要重新播放并跳转
            new_position = max(0, self.current_position - 5000)
            self.seek_to_position(new_position)

    def seek_forward(self):
        """前进5秒"""
        if self.is_playing and self.current_index >= 0:
            new_position = min(self.duration, self.current_position + 5000)
            self.seek_to_position(new_position)

    def seek_to_position(self, position_ms):
        """跳转到指定位置（毫秒）"""
        if self.current_index >= 0:
            try:
                # pygame.mixer.music.play(start=) 使用秒为单位
                pygame.mixer.music.play(start=position_ms / 1000.0)
                # 设置跳转偏移量，因为 get_pos() 会从 0 开始计算
                self.seek_offset = position_ms
                self.current_position = position_ms
            except Exception as e:
                print(f"跳转失败: {e}")

    def smart_next_shortcut(self):
        """Alt+右方向键: 智能单曲循环模式下的随机下一曲"""
        if self.play_mode == 1:  # 智能单曲循环模式
            self.user_manual_skip = True
            self.smart_next_song()
        else:
            # 其他模式下执行普通的下一曲
            self.next_song()

    def slider_pressed(self):
        """进度条被按下"""
        self.timer.stop()

    def slider_released(self):
        """进度条被释放"""
        position = self.progress_slider.value()
        self.seek_to_position(position)
        self.timer.start()

    def update_progress(self):
        """更新进度"""
        if self.is_playing:
            # 使用 pygame 获取当前播放位置
            try:
                # 先检查歌曲是否播放结束
                if not pygame.mixer.music.get_busy():
                    self.on_song_finished()
                    return

                pos = pygame.mixer.music.get_pos()  # 返回毫秒（从当前play()调用开始）
                if pos >= 0:
                    # 加上跳转偏移量得到实际位置
                    actual_pos = pos + self.seek_offset
                    self.current_position = actual_pos
                    self.progress_slider.setValue(actual_pos)
                    self.time_label.setText(self.format_time(actual_pos))
            except:
                pass

    def on_song_finished(self):
        """歌曲播放结束"""
        self.is_playing = False
        if self.play_mode == 0:  # 顺序播放
            # 播放下一首（顺序）
            next_index = self.current_index + 1
            if next_index < len(self.song_list):
                self.play_song_at_index(next_index)
            else:
                self.play_btn.setText("播放 (Alt+P/空格)")
        elif self.play_mode == 1:  # 单曲循环
            self.play_song_at_index(self.current_index)
        elif self.play_mode == 2:  # 随机播放
            self.play_random_song()

    def position_changed(self, position):
        """播放位置改变"""
        self.current_position = position

    def duration_changed(self, duration):
        """播放时长改变"""
        self.duration = duration
        self.progress_slider.setRange(0, duration)
        self.total_time_label.setText(self.format_time(duration))

    # playlist_position_changed 和 media_status_changed 已移除
    # 使用 update_current_song_display 和 on_song_finished 代替

    def format_time(self, ms):
        """格式化时间"""
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def tray_icon_activated(self, reason):
        """系统托盘图标被激活"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

    def show_window(self):
        """切换窗口显示/隐藏（最大化或隐藏）"""
        if self.isVisible() and not self.isMinimized():
            # 窗口可见，隐藏到托盘
            self.hide()
        else:
            # 窗口隐藏或最小化，显示并最大化
            self.show()
            self.setWindowState(Qt.WindowMaximized)
            self.raise_()
            self.activateWindow()

    def closeEvent(self, event):
        """关闭事件"""
        if self.tray_icon and self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            self.quit_application()
            event.accept()

    def save_playlist(self):
        """保存当前播放列表"""
        if self.song_list:
            # 保存完整的歌曲信息（包括自定义名称）
            self.settings.setValue("playlist_full", self.song_list)

            # 保存当前播放位置
            self.settings.setValue("current_index", self.current_index)

            # 保存播放模式
            self.settings.setValue("play_mode", self.play_mode)

            self.settings.setValue("volume", self.volume)

            # 保存当前文件夹名
            folder_name = self.folder_label.text()
            self.settings.setValue("folder_label", folder_name)

    def load_last_playlist(self):
        """加载上次的播放列表"""
        saved_songs = self.settings.value("playlist_full", [])

        if saved_songs and isinstance(saved_songs, list):
            existing_songs = []
            for song_info in saved_songs:
                if isinstance(song_info, dict) and 'path' in song_info:
                    if os.path.exists(song_info['path']):
                        existing_songs.append(song_info)

            if existing_songs:
                self.song_list = existing_songs
                for song_info in existing_songs:
                    display_text = song_info.get('display_name', f"{song_info['title']} - {song_info['artist']}")
                    item = QListWidgetItem(display_text)
                    self.playlist_widget.addItem(item)

                current_index = self.settings.value("current_index", 0, type=int)
                if 0 <= current_index < len(self.song_list):
                    self.current_index = current_index

                play_mode = self.settings.value("play_mode", 0, type=int)
                if 0 <= play_mode <= 2:
                    self.mode_combo.setCurrentIndex(play_mode)

                volume = self.settings.value("volume", 70, type=int)
                if 0 <= volume <= 100:
                    self.volume_slider.setValue(volume)
                    pygame.mixer.music.set_volume(volume / 100.0)

                folder_name = self.settings.value("folder_label", "")
                if folder_name:
                    self.folder_label.setText(folder_name)
                    self.folder_label.setVisible(True)
        else:
            song_paths = self.settings.value("playlist", [])
            if song_paths and isinstance(song_paths, list):
                existing_paths = [p for p in song_paths if os.path.exists(p)]
                if existing_paths:
                    self.add_files_to_playlist(existing_paths)

    def filter_playlist(self):
        """过滤播放列表"""
        search_text = self.search_box.text().lower()
        
        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)
            if search_text in item.text().lower():
                item.setHidden(False)
            else:
                item.setHidden(True)

    def clear_search(self):
        """清除搜索"""
        self.search_box.clear()
        # 显示所有项目
        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)
            item.setHidden(False)

    def focus_search_box(self):
        """聚焦搜索框"""
        self.search_box.setFocus()
        self.search_box.selectAll()
    
    def focus_playlist_from_search(self):
        """从搜索框聚焦到播放列表"""
        self.playlist_widget.setFocus()
        
        # 如果没有选中项，选择第一个可见项
        if not self.playlist_widget.currentItem():
            for i in range(self.playlist_widget.count()):
                item = self.playlist_widget.item(i)
                if not item.isHidden():
                    self.playlist_widget.setCurrentItem(item)
                    break
    
    def locate_current_song(self):
        """定位到正在播放的歌曲"""
        if self.current_index >= 0 and self.current_index < self.playlist_widget.count():
            # 清除搜索框，显示所有歌曲
            self.clear_search()

            # 选中并滚动到当前播放的歌曲
            current_item = self.playlist_widget.item(self.current_index)
            if current_item:
                self.playlist_widget.setCurrentItem(current_item)
                self.playlist_widget.scrollToItem(current_item, QListWidget.PositionAtCenter)
                self.playlist_widget.setFocus()
        else:
            # 如果没有正在播放的歌曲，显示提示
            QMessageBox.information(self, "提示", "当前没有正在播放的歌曲")
    
    def add_to_history(self, index):
        """记录上一曲 - 只保存最后一首歌曲"""
        # 只保存当前歌曲作为"上一曲"
        self.play_history = [index]
        self.history_index = 0
    
    def get_previous_from_history(self):
        """获取上一曲"""
        if len(self.play_history) > 0:
            # 返回保存的上一曲，并清空历史记录避免重复返回
            prev_index = self.play_history[0]
            self.play_history = []
            self.history_index = -1
            return prev_index
        return None
    
    def smart_next_song(self):
        """智能下一曲 - 在智能单曲循环模式下使用"""
        if len(self.song_list) > 0:
            # 将当前播放的歌曲加入历史记录
            if self.current_index >= 0:
                self.add_to_history(self.current_index)

            random_index = random.randint(0, len(self.song_list) - 1)
            # 避免选择相同的歌曲
            while random_index == self.current_index and len(self.song_list) > 1:
                random_index = random.randint(0, len(self.song_list) - 1)
            self.play_song_at_index(random_index)

    def rename_current_item(self):
        """重命名当前选中的项目"""
        current_item = self.playlist_widget.currentItem()
        if current_item:
            self.rename_playlist_item(current_item)

    def delete_current_item(self):
        """删除当前选中的项目"""
        current_item = self.playlist_widget.currentItem()
        if current_item:
            self.delete_playlist_item(current_item)

    def show_context_menu(self, position):
        """显示右键菜单"""
        item = self.playlist_widget.itemAt(position)
        if item is None:
            return
        
        menu = QMenu()
        
        # 重命名动作
        rename_action = QAction("重命名 (Ctrl+R)", self)
        rename_action.triggered.connect(lambda: self.rename_playlist_item(item))
        menu.addAction(rename_action)
        
        # 删除动作
        delete_action = QAction("从列表中删除 (Delete)", self)
        delete_action.triggered.connect(lambda: self.delete_playlist_item(item))
        menu.addAction(delete_action)
        
        menu.addSeparator()
        
        # 播放动作
        play_action = QAction("播放", self)
        play_action.triggered.connect(lambda: self.play_selected_song(item))
        menu.addAction(play_action)
        
        # 显示菜单
        menu.exec_(self.playlist_widget.mapToGlobal(position))

    def rename_playlist_item(self, item):
        """重命名播放列表项目"""
        current_text = item.text()
        
        # 获取当前项目的索引
        item_index = self.playlist_widget.row(item)
        if item_index < 0 or item_index >= len(self.song_list):
            return
        
        # 显示输入对话框
        new_name, ok = QInputDialog.getText(
            self, "重命名", "请输入新的显示名称:", 
            QLineEdit.Normal, current_text
        )
        
        if ok and new_name.strip():
            # 更新列表项显示
            item.setText(new_name.strip())

            # 更新歌曲信息中的标题
            song_info = self.song_list[item_index]
            song_info['display_name'] = new_name.strip()

            # 如果是当前播放的歌曲，更新显示
            if self.current_index == item_index:
                self.current_song_label.setText(new_name.strip())

            # 保存播放列表
            self.save_playlist()

    def delete_playlist_item(self, item):
        """从播放列表中删除项目"""
        reply = QMessageBox.question(
            self, "确认删除", "确定要从播放列表中删除这首歌曲吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            item_index = self.playlist_widget.row(item)
            if item_index >= 0:
                # 从UI列表中删除
                self.playlist_widget.takeItem(item_index)

                # 从歌曲信息列表中删除
                if item_index < len(self.song_list):
                    del self.song_list[item_index]

                # 如果删除的是当前播放的歌曲，调整索引
                if item_index == self.current_index:
                    pygame.mixer.music.stop()
                    self.is_playing = False
                    self.current_index = -1
                elif item_index < self.current_index:
                    self.current_index -= 1

                # 保存播放列表
                self.save_playlist()

    

    def check_hotkey_conflicts(self):
        """检查快捷键冲突并提供解决方案"""
        # 此方法现在由独立进程处理，主窗口不需要特别处理
        pass

    # monitor_audio_status, restart_audio_if_needed, resume_audio 已移除（使用 pygame 后不需要）

    def show_audio_device_settings(self):
        """显示音频设备设置对话框"""
        msg = QMessageBox(self)
        msg.setWindowTitle("音频设备设置")
        msg.setText("蓝牙耳机播放问题解决方案:")
        msg.setInformativeText(
            "如果您的蓝牙耳机播放声音断断续续，可以尝试以下方法：\n\n"
            "1. 在Windows音频设置中：\n"
            "   - 右键点击系统托盘中的音量图标\n"
            "   - 选择'声音设置'\n"
            "   - 在'输出'部分选择您的蓝牙耳机\n"
            "   - 点击'设备属性'，调整音频质量\n\n"
            "2. 在蓝牙设置中：\n"
            "   - 断开并重新连接蓝牙耳机\n"
            "   - 确保蓝牙驱动程序是最新的\n\n"
            "3. 如果问题持续，请尝试：\n"
            "   - 重新启动播放器\n"
            "   - 重新启动蓝牙服务\n"
            "   - 将音频文件转换为更兼容的格式(MP3/WAV)"
        )
        msg.setIcon(QMessageBox.Information)
        msg.addButton("打开Windows音频设置", QMessageBox.ActionRole)
        msg.addButton("确定", QMessageBox.AcceptRole)
        
        result = msg.exec_()
        if result == 0:  # 用户点击了"打开Windows音频设置"
            try:
                import subprocess
                subprocess.run(['ms-settings:sound'], shell=True)
            except Exception as e:
                print(f"无法打开Windows音频设置: {e}")
                QMessageBox.warning(self, "错误", "无法打开Windows音频设置，请手动打开。")
    
    def quit_application(self):
        """退出应用程序"""
        # 停止全局快捷键进程
        if self.global_hotkey_process:
            self.global_hotkey_process.stop()

        # 停止事件监听定时器
        if hasattr(self, 'hotkey_event_timer'):
            self.hotkey_event_timer.stop()

        # 停止 pygame
        try:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except:
            pass

        # 保存当前播放列表
        self.save_playlist()

        # 隐藏系统托盘图标
        if self.tray_icon:
            self.tray_icon.hide()

        QApplication.quit()


def main():
    # 不再强制使用WMF后端（可能导致某些文件无法播放）
    # os.environ['QT_MULTIMEDIA_PREFERRED_PLUGINS'] = 'windowsmediafoundation'
    # 抑制 Qt 视频相关的警告信息
    os.environ['QT_LOGGING_RULES'] = '*.debug=false;qt.multimedia.*=false'

    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        # 设置应用程序图标
        def get_resource_path(relative_path):
            try:
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.abspath(".")
            return os.path.join(base_path, relative_path)

        icon_path = get_resource_path("1024x1024.png")
        app.setWindowIcon(QIcon(icon_path))

        player = MusicPlayer()
        player.show()

        # 保持player引用，防止被垃圾回收
        app.player = player

        sys.exit(app.exec_())
    except Exception as e:
        print(f"程序错误: {e}")
        import traceback
        traceback.print_exc()
        input("按回车键退出...")


if __name__ == "__main__":
    # Windows multiprocessing 支持 - 必须在最开始调用
    multiprocessing.freeze_support()
    main() 
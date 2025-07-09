import sys
import os
import random
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QPushButton, QLabel, QSlider, QListWidget, 
                             QFileDialog, QMessageBox, QSystemTrayIcon, QMenu, 
                             QAction, QComboBox, QSplitter, QListWidgetItem, QShortcut,
                             QLineEdit, QInputDialog)
from PyQt5.QtCore import Qt, QTimer, QUrl, pyqtSignal, QSettings
from PyQt5.QtGui import QIcon, QPixmap, QFont, QKeySequence
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QMediaPlaylist
import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError


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
        self.setWindowTitle("音乐播放器:2025/07/09-03")
        self.setGeometry(100, 100, 800, 600)
        
        # 设置应用图标
        icon_path = self.get_resource_path("1328x1328.png")
        self.setWindowIcon(QIcon(icon_path))
        
        # 设置默认最大化
        self.showMaximized()
        
        # 初始化媒体播放器
        self.player = QMediaPlayer()
        self.playlist = QMediaPlaylist()
        self.player.setPlaylist(self.playlist)
        
        # 播放状态
        self.is_playing = False
        self.current_position = 0
        self.duration = 0
        self.volume = 70
        
        # 播放模式 0:顺序播放 1:单曲循环 2:随机播放
        self.play_mode = 0
        
        # 歌曲信息列表
        self.song_list = []
        
        # 初始化设置
        self.settings = QSettings("MusicPlayer", "PlaylistMemory")
        
        # 初始化UI
        self.init_ui()
        
        # 初始化系统托盘
        self.init_tray()
        
        # 初始化快捷键
        self.init_shortcuts()
        
        # 连接信号
        self.connect_signals()
        
        # 定时器更新进度
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(1000)
        
        # 加载上次的播放列表
        self.load_last_playlist()

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
        
        # 播放模式选择
        mode_label = QLabel("播放模式 (Alt+M/L):")
        top_layout.addWidget(mode_label)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["顺序播放", "单曲循环", "随机播放"])
        self.mode_combo.currentIndexChanged.connect(self.change_play_mode)
        self.mode_combo.setToolTip("播放模式: Alt+M(循环切换) Alt+L(打开下拉菜单)")
        top_layout.addWidget(self.mode_combo)
        
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
        search_layout.addWidget(QLabel("搜索:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("输入歌曲名称或艺术家...")
        self.search_box.textChanged.connect(self.filter_playlist)
        search_layout.addWidget(self.search_box)
        
        # 清除搜索按钮
        clear_search_btn = QPushButton("清除")
        clear_search_btn.clicked.connect(self.clear_search)
        search_layout.addWidget(clear_search_btn)
        
        left_layout.addLayout(search_layout)
        
        # 播放列表
        self.playlist_widget = QListWidget()
        self.playlist_widget.itemDoubleClicked.connect(self.play_selected_song)
        self.playlist_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.playlist_widget.customContextMenuRequested.connect(self.show_context_menu)
        left_layout.addWidget(self.playlist_widget)
        
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
        
        self.prev_btn = QPushButton("上一曲 (Alt+B)")
        self.prev_btn.clicked.connect(self.previous_song)
        control_layout.addWidget(self.prev_btn)
        
        self.play_btn = QPushButton("播放 (Alt+P/空格)")
        self.play_btn.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_btn)
        
        self.next_btn = QPushButton("下一曲 (Alt+N)")
        self.next_btn.clicked.connect(self.next_song)
        control_layout.addWidget(self.next_btn)
        
        right_layout.addLayout(control_layout)
        
        # 音量控制
        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("音量 (Alt+U/D):"))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.volume)
        self.volume_slider.valueChanged.connect(self.change_volume)
        self.volume_slider.setToolTip("音量调节 (Alt+U增加, Alt+D减少)")
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
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, "系统托盘", "系统托盘不可用")
            return
        
        # 创建系统托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        
        # 设置图标（使用自定义图标）
        icon_path = self.get_resource_path("1328x1328.png")
        self.tray_icon.setIcon(QIcon(icon_path))
        
        # 创建托盘菜单
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
        
        # 显示托盘图标
        self.tray_icon.show()

    def init_shortcuts(self):
        """初始化快捷键"""
        # Alt+O: 打开文件
        self.open_file_shortcut = QShortcut(QKeySequence("Alt+O"), self)
        self.open_file_shortcut.activated.connect(self.open_file)
        
        # Alt+F: 打开文件夹
        self.open_folder_shortcut = QShortcut(QKeySequence("Alt+F"), self)
        self.open_folder_shortcut.activated.connect(self.open_folder)
        
        # Alt+P: 播放/暂停
        self.play_shortcut = QShortcut(QKeySequence("Alt+P"), self)
        self.play_shortcut.activated.connect(self.toggle_play)
        
        # Alt+B: 上一曲
        self.prev_shortcut = QShortcut(QKeySequence("Alt+B"), self)
        self.prev_shortcut.activated.connect(self.previous_song)
        
        # Alt+N: 下一曲
        self.next_shortcut = QShortcut(QKeySequence("Alt+N"), self)
        self.next_shortcut.activated.connect(self.next_song)
        
        # Alt+M: 切换播放模式
        self.mode_shortcut = QShortcut(QKeySequence("Alt+M"), self)
        self.mode_shortcut.activated.connect(self.cycle_play_mode)
        
        # Alt+L: 打开播放模式下拉菜单
        self.mode_dropdown_shortcut = QShortcut(QKeySequence("Alt+L"), self)
        self.mode_dropdown_shortcut.activated.connect(self.show_mode_dropdown)
        
        # Alt+U: 音量增加
        self.volume_up_shortcut = QShortcut(QKeySequence("Alt+U"), self)
        self.volume_up_shortcut.activated.connect(self.volume_up)
        
        # Alt+D: 音量减少
        self.volume_down_shortcut = QShortcut(QKeySequence("Alt+D"), self)
        self.volume_down_shortcut.activated.connect(self.volume_down)
        
        # 空格键: 播放/暂停
        self.space_shortcut = QShortcut(QKeySequence("Space"), self)
        self.space_shortcut.activated.connect(self.toggle_play)
        
        # 左方向键: 后退5秒
        self.left_shortcut = QShortcut(QKeySequence("Left"), self)
        self.left_shortcut.activated.connect(self.seek_backward)
        
        # 右方向键: 前进5秒
        self.right_shortcut = QShortcut(QKeySequence("Right"), self)
        self.right_shortcut.activated.connect(self.seek_forward)

    def connect_signals(self):
        """连接信号和槽"""
        self.player.stateChanged.connect(self.player_state_changed)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(self.duration_changed)
        self.playlist.currentIndexChanged.connect(self.playlist_position_changed)

    def open_file(self):
        """打开音频文件"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择音频文件", "", 
            "音频文件 (*.mp3 *.wav *.m4a *.flac *.ogg);;所有文件 (*)"
        )
        
        if file_paths:
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
                self.add_files_to_playlist(file_paths)
                # 保存播放列表
                self.save_playlist()
            else:
                QMessageBox.information(self, "提示", "所选文件夹中没有找到音频文件")

    def add_files_to_playlist(self, file_paths):
        """添加文件到播放列表"""
        for file_path in file_paths:
            # 获取歌曲信息
            song_info = self.get_song_info(file_path)
            self.song_list.append(song_info)
            
            # 添加到播放列表
            self.playlist.addMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
            
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
        except Exception as e:
            print(f"读取歌曲信息失败: {e}")
        
        return song_info

    def play_selected_song(self, item):
        """播放选中的歌曲"""
        index = self.playlist_widget.row(item)
        self.playlist.setCurrentIndex(index)
        self.player.play()

    def toggle_play(self):
        """切换播放/暂停"""
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def previous_song(self):
        """上一曲"""
        if self.play_mode == 2:  # 随机播放
            self.play_random_song()
        else:
            self.playlist.previous()

    def next_song(self):
        """下一曲"""
        if self.play_mode == 2:  # 随机播放
            self.play_random_song()
        else:
            self.playlist.next()

    def play_random_song(self):
        """播放随机歌曲"""
        if self.playlist.mediaCount() > 0:
            random_index = random.randint(0, self.playlist.mediaCount() - 1)
            self.playlist.setCurrentIndex(random_index)

    def change_play_mode(self, index):
        """改变播放模式"""
        self.play_mode = index
        if index == 0:  # 顺序播放
            self.playlist.setPlaybackMode(QMediaPlaylist.Sequential)
        elif index == 1:  # 单曲循环
            self.playlist.setPlaybackMode(QMediaPlaylist.CurrentItemInLoop)
        elif index == 2:  # 随机播放
            self.playlist.setPlaybackMode(QMediaPlaylist.Sequential)
        
        # 保存播放模式
        self.settings.setValue("play_mode", self.play_mode)

    def change_volume(self, value):
        """改变音量"""
        self.volume = value
        self.player.setVolume(value)
        self.volume_label.setText(f"{value}%")
        
        # 保存音量设置
        self.settings.setValue("volume", self.volume)

    def cycle_play_mode(self):
        """循环切换播放模式"""
        current_mode = self.mode_combo.currentIndex()
        next_mode = (current_mode + 1) % 3
        self.mode_combo.setCurrentIndex(next_mode)

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
        current_position = self.player.position()
        new_position = max(0, current_position - 5000)  # 5秒 = 5000毫秒
        self.player.setPosition(new_position)

    def seek_forward(self):
        """前进5秒"""
        current_position = self.player.position()
        duration = self.player.duration()
        new_position = min(duration, current_position + 5000)  # 5秒 = 5000毫秒
        self.player.setPosition(new_position)

    def slider_pressed(self):
        """进度条被按下"""
        self.timer.stop()

    def slider_released(self):
        """进度条被释放"""
        position = self.progress_slider.value()
        self.player.setPosition(position)
        self.timer.start()

    def update_progress(self):
        """更新进度"""
        if self.player.state() == QMediaPlayer.PlayingState:
            position = self.player.position()
            self.progress_slider.setValue(position)
            self.time_label.setText(self.format_time(position))

    def player_state_changed(self, state):
        """播放器状态改变"""
        if state == QMediaPlayer.PlayingState:
            self.play_btn.setText("暂停 (Alt+P/空格)")
            self.is_playing = True
        else:
            self.play_btn.setText("播放 (Alt+P/空格)")
            self.is_playing = False

    def position_changed(self, position):
        """播放位置改变"""
        self.current_position = position

    def duration_changed(self, duration):
        """播放时长改变"""
        self.duration = duration
        self.progress_slider.setRange(0, duration)
        self.total_time_label.setText(self.format_time(duration))

    def playlist_position_changed(self, position):
        """播放列表位置改变"""
        if 0 <= position < len(self.song_list):
            song_info = self.song_list[position]
            # 优先显示自定义名称，否则显示原始信息
            display_text = song_info.get('display_name', f"{song_info['title']} - {song_info['artist']}")
            self.current_song_label.setText(display_text)
            
            # 高亮当前播放的歌曲
            for i in range(self.playlist_widget.count()):
                item = self.playlist_widget.item(i)
                if i == position:
                    item.setBackground(Qt.lightGray)
                else:
                    item.setBackground(Qt.white)
            
            # 保存当前播放位置
            self.settings.setValue("current_index", position)

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
        """显示窗口"""
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        """关闭事件"""
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()

    def save_playlist(self):
        """保存当前播放列表"""
        if self.song_list:
            # 保存完整的歌曲信息（包括自定义名称）
            self.settings.setValue("playlist_full", self.song_list)
            
            # 保存当前播放位置
            current_index = self.playlist.currentIndex()
            self.settings.setValue("current_index", current_index)
            
            # 保存播放模式
            self.settings.setValue("play_mode", self.play_mode)
            
            # 保存音量
            self.settings.setValue("volume", self.volume)
            
            print(f"已保存播放列表，共{len(self.song_list)}首歌曲")

    def load_last_playlist(self):
        """加载上次的播放列表"""
        # 尝试加载完整的播放列表信息
        saved_songs = self.settings.value("playlist_full", [])
        
        if saved_songs and isinstance(saved_songs, list):
            # 过滤存在的文件并恢复信息
            existing_songs = []
            for song_info in saved_songs:
                if isinstance(song_info, dict) and 'path' in song_info:
                    if os.path.exists(song_info['path']):
                        existing_songs.append(song_info)
                    else:
                        print(f"文件不存在，跳过: {song_info['path']}")
            
            if existing_songs:
                # 直接设置歌曲列表
                self.song_list = existing_songs
                
                # 重建播放列表和UI
                for song_info in existing_songs:
                    # 添加到播放列表
                    self.playlist.addMedia(QMediaContent(QUrl.fromLocalFile(song_info['path'])))
                    
                    # 添加到UI列表
                    display_text = song_info.get('display_name', f"{song_info['title']} - {song_info['artist']}")
                    item = QListWidgetItem(display_text)
                    self.playlist_widget.addItem(item)
                
                # 恢复播放位置
                current_index = self.settings.value("current_index", 0, type=int)
                if 0 <= current_index < self.playlist.mediaCount():
                    self.playlist.setCurrentIndex(current_index)
                
                # 恢复播放模式
                play_mode = self.settings.value("play_mode", 0, type=int)
                if 0 <= play_mode <= 2:
                    self.mode_combo.setCurrentIndex(play_mode)
                
                # 恢复音量
                volume = self.settings.value("volume", 70, type=int)
                if 0 <= volume <= 100:
                    self.volume_slider.setValue(volume)
                
                print(f"已加载上次播放列表，共{len(existing_songs)}首歌曲")
            else:
                print("上次播放列表中的文件都不存在")
        else:
            # 尝试加载旧格式的播放列表（仅路径）
            song_paths = self.settings.value("playlist", [])
            if song_paths and isinstance(song_paths, list):
                existing_paths = []
                for path in song_paths:
                    if os.path.exists(path):
                        existing_paths.append(path)
                    else:
                        print(f"文件不存在，跳过: {path}")
                
                if existing_paths:
                    self.add_files_to_playlist(existing_paths)
                    print(f"已加载旧格式播放列表，共{len(existing_paths)}首歌曲")
                else:
                    print("上次播放列表中的文件都不存在")
            else:
                print("没有找到上次的播放列表")

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

    def show_context_menu(self, position):
        """显示右键菜单"""
        item = self.playlist_widget.itemAt(position)
        if item is None:
            return
        
        menu = QMenu()
        
        # 重命名动作
        rename_action = QAction("重命名", self)
        rename_action.triggered.connect(lambda: self.rename_playlist_item(item))
        menu.addAction(rename_action)
        
        # 删除动作
        delete_action = QAction("从列表中删除", self)
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
            if self.playlist.currentIndex() == item_index:
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
                
                # 从播放列表中删除
                self.playlist.removeMedia(item_index)
                
                # 从歌曲信息列表中删除
                if item_index < len(self.song_list):
                    del self.song_list[item_index]
                
                # 保存播放列表
                self.save_playlist()

    def quit_application(self):
        """退出应用程序"""
        # 保存当前播放列表
        self.save_playlist()
        self.tray_icon.hide()
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭最后一个窗口时不退出程序
    
    # 设置应用程序图标（用于任务栏）
    def get_resource_path(relative_path):
        """获取资源文件路径，支持PyInstaller打包"""
        try:
            # PyInstaller创建临时文件夹，将路径存储在_MEIPASS中
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)
    
    icon_path = get_resource_path("1328x1328.png")
    app.setWindowIcon(QIcon(icon_path))
    
    player = MusicPlayer()
    player.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main() 
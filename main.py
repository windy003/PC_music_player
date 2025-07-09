import sys
import os
import random
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QPushButton, QLabel, QSlider, QListWidget, 
                             QFileDialog, QMessageBox, QSystemTrayIcon, QMenu, 
                             QAction, QComboBox, QSplitter, QListWidgetItem)
from PyQt5.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QFont
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QMediaPlaylist
import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError


class MusicPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("音乐播放器")
        self.setGeometry(100, 100, 800, 600)
        
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
        
        # 初始化UI
        self.init_ui()
        
        # 初始化系统托盘
        self.init_tray()
        
        # 连接信号
        self.connect_signals()
        
        # 定时器更新进度
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(1000)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # 顶部按钮区域
        top_layout = QHBoxLayout()
        
        # 打开文件按钮
        self.open_file_btn = QPushButton("打开文件")
        self.open_file_btn.clicked.connect(self.open_file)
        top_layout.addWidget(self.open_file_btn)
        
        # 打开文件夹按钮
        self.open_folder_btn = QPushButton("打开文件夹")
        self.open_folder_btn.clicked.connect(self.open_folder)
        top_layout.addWidget(self.open_folder_btn)
        
        # 播放模式选择
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["顺序播放", "单曲循环", "随机播放"])
        self.mode_combo.currentIndexChanged.connect(self.change_play_mode)
        top_layout.addWidget(self.mode_combo)
        
        top_layout.addStretch()
        main_layout.addLayout(top_layout)
        
        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # 播放列表
        self.playlist_widget = QListWidget()
        self.playlist_widget.itemDoubleClicked.connect(self.play_selected_song)
        splitter.addWidget(self.playlist_widget)
        
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
        self.total_time_label = QLabel("00:00")
        
        progress_layout.addWidget(self.time_label)
        progress_layout.addWidget(self.progress_slider)
        progress_layout.addWidget(self.total_time_label)
        right_layout.addLayout(progress_layout)
        
        # 控制按钮
        control_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("上一曲")
        self.prev_btn.clicked.connect(self.previous_song)
        control_layout.addWidget(self.prev_btn)
        
        self.play_btn = QPushButton("播放")
        self.play_btn.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_btn)
        
        self.next_btn = QPushButton("下一曲")
        self.next_btn.clicked.connect(self.next_song)
        control_layout.addWidget(self.next_btn)
        
        right_layout.addLayout(control_layout)
        
        # 音量控制
        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("音量:"))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.volume)
        self.volume_slider.valueChanged.connect(self.change_volume)
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
        
        # 设置图标（使用默认图标）
        self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_MediaPlay))
        
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
        
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        
        # 显示托盘图标
        self.tray_icon.show()

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
            item = QListWidgetItem(f"{song_info['title']} - {song_info['artist']}")
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

    def change_volume(self, value):
        """改变音量"""
        self.volume = value
        self.player.setVolume(value)
        self.volume_label.setText(f"{value}%")

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
            self.play_btn.setText("暂停")
            self.is_playing = True
        else:
            self.play_btn.setText("播放")
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
            self.current_song_label.setText(f"{song_info['title']} - {song_info['artist']}")
            
            # 高亮当前播放的歌曲
            for i in range(self.playlist_widget.count()):
                item = self.playlist_widget.item(i)
                if i == position:
                    item.setBackground(Qt.lightGray)
                else:
                    item.setBackground(Qt.white)

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
            QMessageBox.information(
                self, "音乐播放器",
                "程序将最小化到系统托盘。要完全退出程序，请在托盘图标上右键选择退出。"
            )
            self.hide()
            event.ignore()

    def quit_application(self):
        """退出应用程序"""
        self.tray_icon.hide()
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭最后一个窗口时不退出程序
    
    player = MusicPlayer()
    player.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main() 
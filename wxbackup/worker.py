from __future__ import annotations

import queue
import copy
import re
import threading
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from playwright.sync_api import sync_playwright

from .collector import Collector
from .model import Store, BackupError, Cancelled
from .backend import ResponseTracker, logged_in_page


def redact(text):
    return re.sub(r'(https?://[^\s?]+)\?[^\s]+', r'\1?[参数已隐藏]', str(text))


class Worker(QThread):
    log = Signal(str)
    status = Signal(str)
    snapshot = Signal(dict)
    progress = Signal(int, int, str)
    busy = Signal(bool)
    error = Signal(str)

    def __init__(self, app_dir: Path):
        super().__init__()
        self.app_dir = app_dir
        self.commands = queue.Queue()
        self.paused = threading.Event()
        self.stopping = threading.Event()
        self.cancel = threading.Event()
        self.context = self.page = None
        self.tracker=ResponseTracker()

    def submit(self, action, root, formats=None):
        self.commands.put((action, root, formats))

    def check(self):
        if self.stopping.is_set() or self.cancel.is_set():
            raise Cancelled('操作已停止；已完成的数据已保存，可重新开始。')
        while self.paused.is_set():
            if self.stopping.is_set() or self.cancel.is_set():
                raise Cancelled('操作已停止；已完成的数据已保存。')
            time.sleep(.15)

    def connect_browser(self, playwright):
        if self.context:
            try:
                self.page.title()
                return
            except Exception:
                try: self.context.close()
                except Exception: pass
                self.context = None
        self.context = playwright.chromium.launch_persistent_context(
            str(self.app_dir / 'data' / 'browser'), channel='msedge', headless=False,
            viewport={'width':1280, 'height':850}, accept_downloads=False)
        self.tracker=ResponseTracker()
        self.context.on('response',self.tracker.capture)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.goto('https://mp.weixin.qq.com/', wait_until='domcontentloaded', timeout=60000)
        self.page.bring_to_front()
        self.status.emit('浏览器已连接，请扫码登录')
        self.log.emit('请在新打开的 Edge 扫码，登录后进入「内容管理 → 发表记录」。')

    def run(self):
        with sync_playwright() as playwright:
            while not self.stopping.is_set():
                try:
                    action, root, formats = self.commands.get(timeout=.15)
                except queue.Empty:
                    if self.context:
                        try:
                            self.page.wait_for_timeout(100)
                            try: self.page=logged_in_page(self.context,self.page)
                            except BackupError: pass
                            url = self.page.url
                            self.status.emit('已登录 · 浏览器已连接' if 'token=' in url else '浏览器已连接 · 等待扫码登录')
                        except Exception:
                            self.status.emit('浏览器已断开，请重新打开登录浏览器')
                    continue
                self.busy.emit(True)
                self.cancel.clear()
                store = None
                try:
                    if action == 'open':
                        self.connect_browser(playwright)
                        continue
                    store = Store(root)
                    if action == 'collect':
                        if not self.context:
                            raise BackupError('请先打开登录浏览器并扫码登录。')
                        self.paused.clear()
                        def collection_progress(n,t,a):
                            self.progress.emit(n,t,f'已采集 {n}/{t} 次发表 · {a} 条记录')
                            self.snapshot.emit(copy.deepcopy(store.data))
                        collector = Collector(self.context, self.page, self.log.emit, collection_progress, self.check, tracker=self.tracker)
                        collector.collect(store)
                        self.page=collector.page
                        self.log.emit('列表数量核对完成，可开始备份。')
                    elif action == 'download':
                        from .downloader import Downloader
                        def download_progress(n,t,text):
                            self.progress.emit(n,t,text)
                            self.snapshot.emit(copy.deepcopy(store.data))
                        Downloader(playwright, self.log.emit, download_progress, self.check).run(store, formats)
                    elif action == 'export':
                        pass
                    from .report import export_reports
                    export_reports(store)
                    self.snapshot.emit(store.data)
                except Exception as exc:
                    message = redact(str(exc))
                    self.error.emit(message)
                    self.log.emit(f'{type(exc).__name__}: {message}')
                    if store:
                        self.snapshot.emit(store.data)
                        try:
                            from .report import export_reports
                            export_reports(store)
                        except Exception as report_exc:
                            self.log.emit('目录导出失败（请关闭 Excel 后重新导出）：' + redact(report_exc))
                finally:
                    self.busy.emit(False)
            if self.context:
                try: self.context.close()
                except Exception: pass

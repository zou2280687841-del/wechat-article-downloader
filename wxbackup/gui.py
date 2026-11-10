from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QLockFile, QSettings, QTimer
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QFileDialog, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QProgressBar, QMessageBox, QSplitter, QAbstractItemView)

from .model import Store
from .worker import Worker
from . import __version__


class Window(QWidget):
    def __init__(self, app_dir):
        super().__init__()
        self.app_dir = Path(app_dir)
        (self.app_dir/'data').mkdir(parents=True,exist_ok=True)
        self.settings = QSettings(str(self.app_dir/'data'/'settings.ini'), QSettings.Format.IniFormat)
        self.setWindowTitle('微信公众号历史文章备份 v'+__version__)
        self.resize(1180, 800)
        self.setStyleSheet('QWidget {font-family: "Microsoft YaHei UI"; font-size: 10pt;} QPushButton {padding: 7px 12px;} QTableWidget {alternate-background-color:#f1f5f9;}')
        layout=QVBoxLayout(self)
        self.connection=QLabel('浏览器未连接 · 请先打开登录浏览器')
        layout.addWidget(self.connection)
        top=QHBoxLayout(); layout.addLayout(top)
        self.open_button=QPushButton('① 打开登录浏览器')
        self.collect_button=QPushButton('② 获取全部文章列表')
        self.export_button=QPushButton('导出目录与报告')
        for b in (self.open_button,self.collect_button,self.export_button): top.addWidget(b)
        top.addStretch()
        layout.addWidget(QLabel('操作：在程序打开的 Edge 中扫码 → 内容管理 → 发表记录（清空筛选）→ 获取列表 → 核对总数后下载。'))
        row=QHBoxLayout(); layout.addLayout(row)
        row.addWidget(QLabel('下载目录'))
        self.directory=QLineEdit(self.settings.value('directory', str(self.app_dir/'备份')))
        self.choose=QPushButton('选择目录')
        row.addWidget(self.directory,1); row.addWidget(self.choose)
        options=QHBoxLayout(); layout.addLayout(options)
        self.html=QCheckBox('HTML（离线图片）'); self.html.setChecked(True)
        self.pdf=QCheckBox('PDF'); self.pdf.setChecked(True)
        self.start_button=QPushButton('③ 开始 / 重试失败项')
        self.pause_button=QPushButton('暂停'); self.resume_button=QPushButton('继续')
        self.stop_button=QPushButton('停止（保留进度）')
        for w in (self.html,self.pdf,self.start_button,self.pause_button,self.resume_button,self.stop_button): options.addWidget(w)
        self.summary=QLabel('尚未采集。发表次数与文章篇数分别统计；无链接的记录也会保留。')
        layout.addWidget(self.summary)
        self.progress=QProgressBar(); layout.addWidget(self.progress)
        split=QSplitter(Qt.Orientation.Vertical); layout.addWidget(split,1)
        self.table=QTableWidget(0,6)
        self.table.setHorizontalHeaderLabels(['完整标题','发表时间','发表状态','下载状态','原文链接','说明'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0,320); self.table.setColumnWidth(1,155)
        self.table.setColumnWidth(4,210)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        split.addWidget(self.table)
        self.logs=QTextEdit(); self.logs.setReadOnly(True); self.logs.document().setMaximumBlockCount(3000)
        split.addWidget(self.logs); split.setSizes([430,160])
        self.worker=Worker(self.app_dir)
        self.worker.log.connect(self.log)
        self.worker.error.connect(lambda msg: self.log('操作提示：'+msg))
        self.worker.status.connect(self.connection.setText)
        self.worker.snapshot.connect(self.populate)
        self.worker.progress.connect(self.show_progress)
        self.worker.busy.connect(self.set_busy)
        self.worker.start()
        self.open_button.clicked.connect(lambda: self.submit('open'))
        self.collect_button.clicked.connect(lambda: self.submit('collect'))
        self.export_button.clicked.connect(lambda: self.submit('export'))
        self.start_button.clicked.connect(lambda: self.submit('download'))
        self.choose.clicked.connect(self.choose_directory)
        self.pause_button.clicked.connect(self.pause)
        self.resume_button.clicked.connect(self.resume)
        self.stop_button.clicked.connect(self.stop)
        self.directory.editingFinished.connect(self.load_catalog)
        self.set_busy(False)
        self.load_catalog()

    def log(self, message):
        line=f'{datetime.now():%H:%M:%S}  {message}'
        self.logs.append(line.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'))
        path=self.app_dir/'data'/'运行日志.log'; path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and path.stat().st_size > 3_000_000:
            path.replace(path.with_suffix('.previous.log'))
        with path.open('a',encoding='utf-8') as file: file.write(line+'\n')

    def submit(self, action):
        root=self.directory.text().strip()
        if not root:
            self.log('请先选择下载目录。'); return
        formats=[name for name,checkbox in [('html',self.html),('pdf',self.pdf)] if checkbox.isChecked()]
        if action=='download' and not formats:
            self.log('请至少选择一种保存格式。'); return
        self.settings.setValue('directory',root)
        self.set_busy(True)
        self.worker.submit(action,root,formats)

    def set_busy(self, busy):
        self.running=busy
        for w in (self.open_button,self.collect_button,self.export_button,self.start_button,self.choose,self.directory,self.html,self.pdf): w.setEnabled(not busy)
        for w in (self.pause_button,self.resume_button,self.stop_button): w.setEnabled(busy)

    def pause(self):
        self.worker.paused.set(); self.log('已请求暂停；当前网络请求完成后暂停。')

    def resume(self):
        self.worker.paused.clear(); self.log('继续执行。')

    def stop(self):
        self.worker.cancel.set(); self.worker.paused.clear(); self.log('已请求停止，正在保存进度。')

    def choose_directory(self):
        value=QFileDialog.getExistingDirectory(self,'选择备份目录',self.directory.text())
        if value: self.directory.setText(value); self.load_catalog()

    def load_catalog(self):
        try: self.populate(Store(self.directory.text()).data)
        except Exception as exc: self.log('无法加载目录：'+str(exc))

    def populate(self, data):
        articles=data['articles']; self.table.setRowCount(len(articles))
        for row,a in enumerate(articles):
            values=[a['title'],a['date'],a['publish_status'],a['download_status'],a['url'],a.get('error') or '; '.join(a.get('warnings',[])) or a.get('date_note') or a.get('metadata_note','')]
            for col,value in enumerate(values):
                item=QTableWidgetItem(str(value)); item.setToolTip(str(value)); self.table.setItem(row,col,item)
        meta=data.get('collection',{})
        self.summary.setText(f'发表记录：{meta.get("collected_publications",0)} / {meta.get("expected_publications","未知")} 次 · 文章/异常记录 {len(articles)} 条 · '+('列表核对完成' if meta.get('complete') else '列表尚未完整核对'))

    def show_progress(self, n, total, text):
        self.progress.setRange(0,max(total,1)); self.progress.setValue(n); self.progress.setFormat(text)

    def closeEvent(self,event):
        if self.worker.isRunning():
            if self.running:
                self.log('正在停止任务并保存数据，完成后可关闭窗口。')
                self.worker.cancel.set(); self.worker.paused.clear(); event.ignore(); return
            self.worker.stopping.set()
            if not self.worker.wait(5000):
                event.ignore(); QTimer.singleShot(1000,self.close); return
        event.accept()


def run(app_dir):
    app=QApplication(sys.argv)
    lock=QLockFile(str(Path(app_dir)/'data'/'application.lock'))
    (Path(app_dir)/'data').mkdir(parents=True,exist_ok=True)
    if not lock.tryLock(100):
        QMessageBox.information(None,'程序已运行','此项目已有一个备份窗口，请切换到该窗口。'); return
    window=Window(app_dir); window.show()
    # Windows launchers may supply SW_HIDE. A second explicit show restores
    # this interactive window even when the launcher itself has no console.
    def reveal():
        window.showNormal()
        window.raise_()
        window.activateWindow()
    QTimer.singleShot(300, reveal)
    if '--login' in sys.argv:
        QTimer.singleShot(500, lambda: window.submit('open'))
    sys.exit(app.exec())

"""Packaged runtime smoke test, explicitly invoked from the development CLI."""
import json
from pathlib import Path


def run_smoke(root):
    root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True)
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from playwright.sync_api import sync_playwright
    from .gui import Window
    from .model import Store
    from .report import export_reports
    app=QApplication.instance() or QApplication([])
    window=Window(root)
    window.show(); app.processEvents()
    assert window.open_button.isEnabled() and window.collect_button.isEnabled()
    window.pause(); assert window.worker.paused.is_set()
    window.resume(); assert not window.worker.paused.is_set()
    window.grab().save(str(root/'gui-preview.png'))
    window.close(); app.processEvents()
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page()
        page.set_content('<meta charset="utf-8"><h1>微信公众号备份测试</h1><table><tr><td>测试正文</td></tr></table>')
        page.pdf(path=str(root/'runtime-test.pdf'),format='A4',print_background=True)
        browser.close()
    export_reports(Store(root/'backup'))
    (root/'smoke-result.json').write_text(json.dumps({'qt_gui':True,'pause_resume':True,'playwright_edge_pdf':True,'excel':True},indent=2),encoding='utf-8')

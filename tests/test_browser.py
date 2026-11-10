"""End-to-end browser tests against a local server; never logs into a real account."""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import sync_playwright
from openpyxl import load_workbook

from wxbackup.collector import Collector
from wxbackup.downloader import Downloader, valid_file
from wxbackup.model import Store, BackupError, Cancelled
from wxbackup.report import export_reports
from tests.test_collection import payload


@pytest.fixture(scope='module')
def server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            if self.path.startswith('/list'):
                start=int(parse_qs(urlsplit(self.path).query).get('begin',['0'])[0])
                body=json.dumps(payload(start)).encode(); mime='application/json'
            elif self.path.startswith('/pixel'):
                body=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/h9sAAAAASUVORK5CYII='); mime='image/png'
            elif self.path.startswith('/missing'):
                self.send_response(404); self.end_headers(); return
            else:
                body='''<!doctype html><meta charset="utf-8"><style>#js_content{font-family:Arial;color:rgb(180, 0, 0);font-size:18px;}td{border:1px solid #555}</style>
<div id="js_article"><h1 id="activity-name">中文完整标题</h1><div id="js_content"><p>中文正文 / offline backup</p>
<table><tr><td>表格甲</td><td>表格乙</td></tr></table><img data-src="/pixel" src="/pixel">
<section style="background-image:url('/pixel')">背景图片</section>
<script>window.fixture=true</script><iframe src="about:blank"></iframe></div></div>'''.encode(); mime='text/html; charset=utf-8'
            self.send_response(200); self.send_header('Content-Type',mime); self.end_headers(); self.wfile.write(body)
    instance=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=instance.serve_forever,daemon=True).start()
    yield f'http://127.0.0.1:{instance.server_port}'
    instance.shutdown()


@pytest.fixture(scope='module')
def pw():
    with sync_playwright() as p: yield p


def test_real_browser_collects_all_pages(pw,server,tmp_path):
    browser=pw.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context(); page=context.new_page()
    class LocalCollector(Collector):
        def discover(self): return server+'/list?begin=0&count=10'
        def wait(self,seconds): self.checkpoint()
    try:
        data=LocalCollector(context,page).collect(Store(tmp_path))
        assert data['collection']['complete'] and len(data['articles'])==190
    finally: browser.close()


def test_discover_actual_browser_response(pw):
    browser=pw.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context(); page=context.new_page()
    base='https://mp.weixin.qq.com/cgi-bin/appmsgpublish'
    def route(request):
        if 'sub_action=list_ex' in request.request.url:
            request.fulfill(json=payload())
        else:
            request.fulfill(content_type='text/html',body='<script>fetch("'+base+'?sub_action=list_ex&begin=0&count=10&token=fixture")</script>')
    page.route('https://mp.weixin.qq.com/**',route)
    try:
        page.goto(base+'?token=fixture')
        url=Collector(context,page).discover()
        assert 'list_ex' in url
    finally: browser.close()


def article(url):
    return {'id':'fixture','title':'=中文标题测试','date':'2025-01-01 08:00:00','url':url,'group_ids':['1'],
            'publish_status':'已发表','download_status':'待下载','error':'','files':{}}


def test_offline_html_pdf_excel_and_resume(pw,server,tmp_path):
    store=Store(tmp_path); a=article(server+'/article')
    store.data.update(articles=[a],collection={'complete':True,'expected_publications':1,'collected_publications':1,'pages':1})
    downloader=Downloader(pw); downloader.run(store,['html','pdf'])
    folder=store.folder(a); text=(folder/'article.html').read_text('utf-8')
    assert 'data:image/png;base64,' in text
    assert '<script' not in text and '<iframe' not in text
    assert 'rgb(180, 0, 0)' in text and '<table' in text
    assert '视频/音频' in a['warnings'][0]
    assert (folder/'article.pdf').read_bytes().startswith(b'%PDF')
    assert valid_file(folder/'article.html',a['files']['html'])
    # Offline render with networking blocked must display body, tables and images.
    browser=pw.chromium.launch(channel='msedge',headless=True)
    try:
        page=browser.new_page(); network=[]
        page.on('request',lambda request:network.append(request.url))
        page.goto((folder/'article.html').as_uri()); page.wait_for_timeout(300)
        assert page.locator('img').evaluate('(i)=>i.complete && i.naturalWidth>0')
        assert not [u for u in network if u.startswith('http')]
        page.screenshot(path=str(tmp_path/'offline-preview.png'),full_page=True)
    finally: browser.close()
    export_reports(store)
    book=load_workbook(tmp_path/'文章目录.xlsx')
    assert book.active['A2'].value=='=中文标题测试' and book.active['A2'].data_type=='s'
    # A completed clean artifact skips network; corruption triggers repair.
    a['warnings']=[]; stamp=(folder/'article.pdf').stat().st_mtime_ns
    Downloader(pw).run(store,['html','pdf'])
    assert (folder/'article.pdf').stat().st_mtime_ns==stamp
    (folder/'article.html').write_text('broken')
    Downloader(pw).run(store,['html'])
    assert valid_file(folder/'article.html',a['files']['html'])


def test_missing_image_is_partial(pw,server,tmp_path):
    browser=pw.chromium.launch(channel='msedge',headless=True); context=browser.new_context()
    d=Downloader(pw); d.page=context.new_page()
    try:
        document,warnings=d.offline_html('<div><img src="/missing"></div>',article(server+'/article'),context)
        assert warnings and '图片未保存' in warnings[0]
        assert 'src="http' not in document
    finally: browser.close()


def test_incomplete_catalog_refused(pw,tmp_path):
    with pytest.raises(BackupError,match='核对'):
        Downloader(pw).run(Store(tmp_path),['html'])

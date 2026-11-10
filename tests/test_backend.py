import json
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import sync_playwright

from wxbackup.backend import ResponseTracker, bootstrap, logged_in_page
from wxbackup.collector import Collector
from wxbackup.model import Store, BackupError
from tests.test_collection import payload


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        yield browser
        browser.close()


def install_html_route(context):
    def route(r):
        parts=urlsplit(r.request.url)
        if parts.path.endswith('/appmsgpublish'):
            start=int(parse_qs(parts.query).get('begin',['0'])[0])
            data=payload(start)
            # This page renders the list in the document itself; no list XHR.
            body='<script>window.wx={cgiData:'+json.dumps(data)+'};</script><div>发表记录</div>'
        else:
            body='<div>首页</div>'
        r.fulfill(content_type='text/html',body=body)
    context.route('https://mp.weixin.qq.com/**',route)


def test_server_rendered_ten_pages_without_xhr(browser,tmp_path):
    context=browser.new_context(); install_html_route(context)
    page=context.new_page()
    page.goto('https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list&begin=0&token=secret-fixture')
    try:
        collector=Collector(context,page)
        collector.wait=lambda seconds:None
        data=collector.collect(Store(tmp_path))
        assert collector.transport=='navigation'
        assert data['collection']['complete'] and data['collection']['pages']==10
        assert len(data['articles'])==190
        assert 'secret-fixture' not in (tmp_path/'采集诊断.json').read_text('utf-8')
    finally: context.close()


def test_select_popup_backend_instead_of_original_tab(browser,tmp_path):
    context=browser.new_context(); install_html_route(context)
    original=context.new_page(); original.goto('https://mp.weixin.qq.com/?token=fixture')
    popup=context.new_page(); popup.goto('https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list&begin=0&token=fixture')
    try:
        assert logged_in_page(context,original)==popup
        collector=Collector(context,original)
        template=collector.discover()
        assert collector.page==popup and collector.transport=='navigation'
        assert '/appmsgpublish' in template
    finally: context.close()


def test_html_filter_is_rejected(browser):
    context=browser.new_context(); install_html_route(context)
    page=context.new_page(); page.goto('https://mp.weixin.qq.com/cgi-bin/appmsgpublish?token=fixture&query=filtered')
    try:
        with pytest.raises(BackupError,match='筛选'): Collector(context,page).discover()
    finally: context.close()


def test_tracker_preserves_parser_failure_reason(browser):
    context=browser.new_context(); tracker=ResponseTracker(); context.on('response',tracker.capture)
    context.route('https://mp.weixin.qq.com/**',lambda r:r.fulfill(json={'publish_page':{'publish_list':[]}}))
    page=context.new_page()
    try:
        page.goto('https://mp.weixin.qq.com/cgi-bin/appmsgpublish?token=private-token')
        page.wait_for_timeout(100)
        assert '总数' in tracker.notes[-1]['parse_error']
        assert 'private-token' not in json.dumps(tracker.notes)
        assert not tracker.responses
    finally: context.close()

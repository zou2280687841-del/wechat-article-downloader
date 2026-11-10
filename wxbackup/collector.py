from __future__ import annotations

import math
import time
import json
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from .model import BackupError, Cancelled, parse_publish_page, merge_articles, atomic_json
from .backend import ResponseTracker, bootstrap, logged_in_page, diagnostic, check_unfiltered


class Collector:
    def __init__(self, context, page, log=print, progress=lambda *x: None, checkpoint=lambda: None, tracker=None):
        self.context, self.page = context, page
        self.log, self.progress, self.checkpoint = log, progress, checkpoint
        self.tracker=tracker
        self.transport='request'

    def wait(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.checkpoint()
            self.page.wait_for_timeout(200)

    def discover(self):
        """Support popup tabs, previously observed XHRs, and HTML bootstrap data."""
        self.page=logged_in_page(self.context,self.page)
        tracker=self.tracker or ResponseTracker()
        local=self.tracker is None
        if local: self.context.on('response',tracker.capture)
        try:
            parts = urlsplit(self.page.url)
            token=parse_qs(parts.query)['token'][0]
            if parts.path.endswith('/appmsgpublish'): check_unfiltered(self.page.url)
            self.log('已识别登录标签页：'+parts.path+'；开始检查列表来源')
            if parts.path.endswith('/appmsgpublish') and bootstrap(self.page) is not None:
                self.transport='navigation'
                self.log('识别到页面内置发表记录数据，使用页面分页采集')
                return self.page.url
            if parts.path.endswith('/appmsgpublish'):
                self.page.reload(wait_until='domcontentloaded', timeout=45000)
            else:
                # Backend labels may change; leave a clear manual route when unavailable.
                for label in ('内容管理', '发表记录'):
                    locator = self.page.get_by_text(label, exact=True)
                    if locator.count():
                        locator.first.click(timeout=10000)
                        self.wait(1)
            end = time.monotonic() + 5
            while not tracker.responses and time.monotonic() < end:
                self.wait(.25)
            self.page=logged_in_page(self.context,self.page)
            found=[url for url,method in tracker.responses if method=='GET' and not parse_qs(urlsplit(url).query).get('fakeid')]
            if not found:
                if urlsplit(self.page.url).path.endswith('/appmsgpublish') and bootstrap(self.page) is not None:
                    self.transport='navigation'
                    self.log('识别到页面内置数据，使用页面分页采集')
                    return self.page.url
                # This is the account's own publication page, not the external
                # account article-selection dialog. All requests are read-only.
                own_url='https://mp.weixin.qq.com/cgi-bin/appmsgpublish?'+urlencode({'sub':'list','begin':0,'count':10,'token':token,'lang':'zh_CN'})
                self.log('没有独立列表请求，正在读取本账号发表记录页内置数据')
                self.page.goto(own_url,wait_until='domcontentloaded',timeout=45000)
                self.wait(1)
                if bootstrap(self.page) is not None:
                    self.transport='navigation'
                    return own_url
                found=[url for url,method in tracker.responses if method=='GET' and not parse_qs(urlsplit(url).query).get('fakeid')]
                if not found:
                    errors=[n.get('parse_error') for n in tracker.notes if n.get('parse_error')]
                    reason='；'.join(dict.fromkeys(errors))
                    raise BackupError('后台未提供可识别的发表记录数据。'+(reason+'。' if reason else '')+'已保存采集诊断.json，请用此文件继续适配。')
            url = found[-1]
            check_unfiltered(url)
            return url
        finally:
            if local: self.context.remove_listener('response', tracker.capture)
            self.last_diagnostic=diagnostic(self.context,tracker)

    def fetch(self, template, begin, count):
        parts = urlsplit(template)
        query = parse_qs(parts.query, keep_blank_values=True)
        query.update(begin=[str(begin)], count=[str(count)])
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), ''))
        for attempt in range(4):
            self.checkpoint()
            try:
                if self.transport=='navigation':
                    self.page.goto(url,wait_until='domcontentloaded',timeout=45000)
                    self.wait(.5)
                    data=bootstrap(self.page)
                    if data is None:
                        raise BackupError('发表记录页面没有可识别的内置列表数据')
                    return data
                response = self.context.request.get(url, timeout=45000,
                    headers={'Referer':self.page.url if self.page else 'https://mp.weixin.qq.com/', 'X-Requested-With':'XMLHttpRequest'})
                try:
                    if not response.ok:
                        raise BackupError(f'列表 HTTP {response.status}')
                    data = response.json()
                finally:
                    response.dispose()
                if data.get('base_resp', {}).get('ret') == 200013:
                    raise BackupError('后台限流，暂缓重试')
                parse_publish_page(data)
                return data
            except Cancelled:
                raise
            except Exception as exc:
                if attempt == 3:
                    raise BackupError(f'第 {begin // count + 1} 页失败：{exc}') from exc
                self.log(f'列表请求失败（{attempt+1}/4），等待后重试：{type(exc).__name__}')
                self.wait(20 if '限流' in str(exc) else 2 ** (attempt+1))

    def collect(self, store):
        try:
            template = self.discover()
        finally:
            if hasattr(self,'last_diagnostic'):
                atomic_json(store.root/'采集诊断.json',self.last_diagnostic)
        count = 10
        old = {a['id']: a for a in store.data['articles']}
        history_path = store.root / '下载续传索引.json'
        if history_path.exists():
            history = json.loads(history_path.read_text('utf-8'))
            old = {**history, **old}
        # Retain download checksums even if a new collection is interrupted.
        atomic_json(history_path, old)
        merged, seen, signatures = {}, set(), set()
        meta = {'complete': False, 'expected_publications': None, 'collected_publications': 0,
                'pages': 0, 'started_at': datetime.now().isoformat(timespec='seconds'), 'error': ''}
        store.data = {'schema': 1, 'collection': meta, 'articles': []}
        begin, total, first_groups = 0, None, None
        try:
            while total is None or begin < total:
                payload = self.fetch(template, begin, count)
                new_total, groups, articles = parse_publish_page(payload)
                if total is not None and new_total != total:
                    raise BackupError('采集期间发表总数发生变化，请重新采集，避免翻页遗漏。')
                total = new_total
                if first_groups is None:
                    first_groups = tuple(groups)
                if not groups and begin < total:
                    raise BackupError('提前遇到空页，采集未完成。')
                signature = tuple(groups)
                if groups and (signature in signatures or any(g in seen for g in groups)):
                    raise BackupError('翻页出现重复发表记录，后台可能忽略分页或列表有变化；未标记为完整。')
                signatures.add(signature)
                seen.update(groups)
                merge_articles(merged, articles)
                # Preserve format completion; never let an old account/title enter a new list.
                for key, item in merged.items():
                    if key in old:
                        for field in ('files', 'download_status', 'error', 'warnings'):
                            if field in old[key]:
                                item[field] = old[key][field]
                begin += len(groups)
                meta.update(expected_publications=total, collected_publications=len(seen), pages=meta['pages']+1)
                store.data['articles'] = list(merged.values())
                store.save()
                self.progress(len(seen), total, len(merged))
                self.log(f'已核对 {len(seen)}/{total} 次发表，获得 {len(merged)} 条文章/异常记录')
                # Raw payload intentionally omits request URL/token/cookies.
                atomic_json(store.root / '采集证据' / f'page_{meta["pages"]:03}.json', payload)
                if total == 0:
                    break
                self.wait(1.2)
            if len(seen) != total:
                raise BackupError(f'发表记录数量不一致：{len(seen)}/{total}')
            # Re-read page zero to detect head insertions/deletions during collection.
            check_total, check_groups, _ = parse_publish_page(self.fetch(template, 0, count))
            if check_total != total or tuple(check_groups) != first_groups:
                raise BackupError('采集结束时列表已变化，请重新采集。')
            if merged and all(a.get('metadata_note') and not a['url'] for a in merged.values()):
                raise BackupError('发表次数已核对，但未解析出任何文章详情；列表不标记为完整，请保留采集证据进行适配。')
            meta['complete'] = True
            meta['finished_at'] = datetime.now().isoformat(timespec='seconds')
        except Exception as exc:
            meta['error'] = str(exc)
            raise
        finally:
            store.save()
        return store.data

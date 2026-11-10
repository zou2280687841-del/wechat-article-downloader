from __future__ import annotations

import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


class BackupError(RuntimeError):
    pass


class Cancelled(BackupError):
    pass


def digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]


def canonical_url(url: str) -> str:
    url = str(url or '').replace('&amp;', '&').strip()
    if url.startswith('//'):
        url = 'https:' + url
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or parts.hostname != 'mp.weixin.qq.com':
        return ''
    query = parse_qs(parts.query)
    if all(k in query for k in ('__biz', 'mid', 'idx')):
        return urlunsplit(('https', parts.netloc, parts.path,
                           urlencode({k: query[k][0] for k in ('__biz', 'mid', 'idx')}), ''))
    return urlunsplit(('https', parts.netloc, parts.path, parts.query, ''))


def date_text(value) -> str:
    if not value:
        return ''
    try:
        return datetime.fromtimestamp(float(value), timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError, OSError, OverflowError):
        return str(value)


def safe_name(title: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip(' .')[:65] or '无标题'
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}:
        name = '_' + name
    return name


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'catalog.json'
        self.data = json.loads(self.path.read_text('utf-8')) if self.path.exists() else {'schema': 1, 'articles': [], 'collection': {}}

    def save(self):
        atomic_json(self.path, self.data)

    def folder(self, article):
        day = article['date'][:10] if re.match(r'^\d{4}-\d{2}-\d{2}', article['date']) else '日期待核对'
        return self.root / day / (safe_name(article['title']) + '_' + article['id'])


def decode(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def parse_publish_page(payload: dict):
    ret = payload.get('base_resp', {}).get('ret', 0)
    if ret:
        raise BackupError(f'后台返回错误 {ret}：{payload.get("base_resp", {}).get("err_msg", "")}')
    page = decode(payload.get('publish_page'))
    if not isinstance(page, dict) or not isinstance(page.get('publish_list'), list):
        raise BackupError('未识别到发表记录数据结构；请确认进入内容管理 → 发表记录。')
    if 'total_count' not in page:
        raise BackupError('后台没有返回发表总数，无法核对完整性。')
    groups, articles = [], []
    for row in page['publish_list']:
        info = decode(row.get('publish_info', row))
        if not isinstance(info, dict):
            raise BackupError('某条发表记录无法解析，停止以避免遗漏。')
        # The account's own backend uses appmsg_info/content_url. The article
        # picker used for other accounts uses appmsgex/link. The UI may expose
        # both arrays with appmsgex empty, so an empty array must not win.
        items = info.get('appmsgex') or info.get('appmsg_info') or row.get('appmsg_info') or row.get('appmsgex') or []
        if not isinstance(items, list):
            raise BackupError('多图文结构发生变化，请保留日志进行适配。')
        group_id = str(info.get('publish_id') or row.get('publish_id') or info.get('msgid') or row.get('msgid') or '')
        if not group_id:
            identity = {'time': info.get('publish_time') or (info.get('sent_info') or {}).get('time'),
                        'items': [(a.get('appmsgid'), a.get('itemidx'), a.get('link') or a.get('content_url') or a.get('url'), a.get('title')) for a in items]}
            group_id = digest(json.dumps(identity if items else info, sort_keys=True, ensure_ascii=False))
        groups.append(group_id)
        sent = info.get('sent_info') or row.get('sent_info') or {}
        published = info.get('publish_time') or sent.get('time') or row.get('publish_time')
        view=info.get('view') or row.get('view') or {}
        page_date=view.get('publishDate','')
        if not isinstance(page_date,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',page_date): page_date=''
        if not items:
            # Preserve empty/deleted/non-article publication records for auditing.
            items = [{'title': info.get('title') or '无可用图文的发表记录（需核对）', '_empty': True}]
        for index, item in enumerate(items):
            link = str(item.get('link') or item.get('content_url') or item.get('url') or '').replace('&amp;', '&')
            canonical = canonical_url(link)
            deleted = any(str(src.get(k, 0)).lower() in ('1', 'true') for src in (row, info, item) for k in ('is_deleted', 'is_delete', 'deleted'))
            key = digest(canonical) if canonical else digest(f'{group_id}:{item.get("appmsgid", "")}:{item.get("itemidx", index)}')
            articles.append({'id': key, 'group_ids': [group_id], 'title': html.unescape(str(item.get('title') or '无标题（需核对）')),
                             'date': date_text(published) if published else page_date,
                             'date_note': '' if published else ('页面仅提供发表日期，未提供具体时间' if page_date else '接口未提供发表时间；未使用创建时间代替'),
                             'url': link if canonical else '', 'publish_status': '已删除' if deleted else ('待核对/无链接' if not canonical else '已发表'),
                             'download_status': '待下载', 'error': '', 'files': {},
                             'metadata_note': '非图文或已清空记录，无法还原文章数量' if item.get('_empty') else ''})
    return int(page['total_count']), groups, articles


def merge_articles(target: dict, articles: list):
    for item in articles:
        old = target.get(item['id'])
        if old:
            old['group_ids'] = sorted(set(old['group_ids'] + item['group_ids']))
            if item['publish_status'] == '已删除':
                old['publish_status'] = '已删除'
        else:
            target[item['id']] = item

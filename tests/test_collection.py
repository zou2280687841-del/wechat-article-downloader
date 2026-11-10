import json
import pytest
from wxbackup.model import parse_publish_page, merge_articles, BackupError, canonical_url, safe_name, Store
from wxbackup.collector import Collector


def payload(start=0, total=95, size=10):
    rows = []
    for i in range(start, min(start+size, total)):
        rows.append({'publish_info': json.dumps({'publish_id': str(i), 'sent_info': {'time': 1735689600},
            'appmsgex': [{'title': f'完整长标题 {i}-{j}', 'link': f'https://mp.weixin.qq.com/s?__biz=B&mid={i}&idx={j}&sn=S',
                         'is_deleted': int(i==3)} for j in (1,2)]})})
    return {'base_resp': {'ret':0}, 'publish_page':json.dumps({'total_count':total, 'publish_list':rows})}


class FakeResponse:
    ok = True
    status = 200
    def __init__(self, data): self.data = data
    def json(self): return self.data
    def dispose(self): pass


class Request:
    def __init__(self, repeat=False, fail=None): self.repeat, self.fail = repeat, fail
    def get(self, url, **kw):
        from urllib.parse import urlsplit, parse_qs
        start = int(parse_qs(urlsplit(url).query)['begin'][0])
        if self.fail is not None and start == self.fail: raise OSError('network')
        return FakeResponse(payload(0 if self.repeat else start))


class Context:
    def __init__(self, **kw): self.request=Request(**kw)


class FixtureCollector(Collector):
    def discover(self): return 'https://mp.weixin.qq.com/cgi-bin/appmsgpublish?begin=0&count=10&token=fixture'
    def wait(self, seconds): self.checkpoint()


def test_ten_pages_and_multi_article(tmp_path):
    store=Store(tmp_path)
    data=FixtureCollector(Context(), None).collect(store)
    assert data['collection']['complete']
    assert data['collection']['pages']==10
    assert data['collection']['collected_publications']==95
    assert len(data['articles'])==190
    assert sum(a['publish_status']=='已删除' for a in data['articles'])==2
    assert data['articles'][0]['date']=='2025-01-01 08:00:00'


def test_repeat_page_not_silent_success(tmp_path):
    store=Store(tmp_path)
    with pytest.raises(BackupError, match='重复'): FixtureCollector(Context(repeat=True), None).collect(store)
    assert not store.data['collection']['complete']
    assert len(store.data['articles'])==20


def test_failure_keeps_checkpoint(tmp_path):
    store=Store(tmp_path)
    with pytest.raises(BackupError): FixtureCollector(Context(fail=20), None).collect(store)
    restored=Store(tmp_path)
    assert len(restored.data['articles'])==40
    assert not restored.data['collection']['complete']


def test_deleted_without_link_and_empty():
    data={'publish_page':{'total_count':2,'publish_list':[
        {'publish_info':{'publish_id':'x','is_deleted':1,'appmsgex':[{'title':'deleted'}]}},
        {'publish_info':{'publish_id':'y','appmsgex':[]}}]}}
    total, groups, articles=parse_publish_page(data)
    assert total==2 and len(groups)==2 and len(articles)==2
    assert articles[0]['publish_status']=='已删除'
    assert articles[1]['metadata_note']


def test_dedup_and_names():
    _,_,articles=parse_publish_page(payload(0,1))
    result={}; merge_articles(result,articles+articles)
    assert len(result)==2
    assert canonical_url(articles[0]['url']+'&scene=1')==canonical_url(articles[0]['url'])
    assert canonical_url('https://evil.example/s')==''
    assert safe_name('CON')=='_CON'
    assert '/' not in safe_name('a/b')


def test_no_publish_time_not_creation_time():
    data={'publish_page':{'total_count':1,'publish_list':[{'publish_info':{'publish_id':'x', 'appmsgex':[{'title':'a','create_time':123}]}}]}}
    assert parse_publish_page(data)[2][0]['date']==''


def test_download_state_survives_interrupted_recollection(tmp_path):
    store=Store(tmp_path)
    FixtureCollector(Context(),None).collect(store)
    key=store.data['articles'][-1]['id']
    store.data['articles'][-1]['files']={'html':{'sha256':'previous','size':10}}
    store.save()
    with pytest.raises(BackupError): FixtureCollector(Context(fail=10),None).collect(store)
    FixtureCollector(Context(),None).collect(Store(tmp_path))
    result=Store(tmp_path)
    assert next(a for a in result.data['articles'] if a['id']==key)['files']['html']['sha256']=='previous'


def test_cancel_keeps_partial_list(tmp_path):
    from wxbackup.model import Cancelled
    store=Store(tmp_path)
    def stop():
        if store.data.get('collection',{}).get('collected_publications',0)>=10: raise Cancelled('stopped')
    with pytest.raises(Cancelled): FixtureCollector(Context(),None,checkpoint=stop).collect(store)
    assert len(Store(tmp_path).data['articles'])==20
    assert not Store(tmp_path).data['collection']['complete']


def test_own_backend_appmsg_info_content_url_and_entities():
    data={'publish_page':{'total_count':1,'publish_list':[{'msgid':123,
        'sent_info':{'time':1735689600},'appmsgex':[],
        'appmsg_info':[
            {'title':'第一篇&nbsp;&amp;完整标题','content_url':'https://mp.weixin.qq.com/s?__biz=B&amp;mid=123&amp;idx=1','is_deleted':False},
            {'title':'已删除的副篇','content_url':'http://mp.weixin.qq.com/s?__biz=B&mid=123&idx=2','is_deleted':True}]}]}}
    total,groups,articles=parse_publish_page(data)
    assert total==1 and groups==['123'] and len(articles)==2
    assert articles[0]['title']=='第一篇\u00a0&完整标题'
    assert articles[0]['url']=='https://mp.weixin.qq.com/s?__biz=B&mid=123&idx=1'
    assert articles[1]['publish_status']=='已删除'
    assert all(not a['metadata_note'] for a in articles)


def test_own_backend_date_only_is_preserved():
    data={'publish_page':{'total_count':1,'publish_list':[{'msgid':123,'sent_info':None,
        'view':{'publishDate':'2021-11-23'},'appmsg_info':[{'title':'文章','content_url':'https://mp.weixin.qq.com/s/fixture'}]}]}}
    article=parse_publish_page(data)[2][0]
    assert article['date']=='2021-11-23'
    assert '未提供具体时间' in article['date_note']


def test_free_publish_info_keeps_sibling_article_details():
    data={'publish_page':{'total_count':1,'publish_list':[{'msgid':123,
        'publish_info':{'publish_id':123},'appmsgex':[],
        'view':{'publishDate':'2021-11-23'},
        'appmsg_info':[{'title':'独立发表文章','content_url':'https://mp.weixin.qq.com/s/fixture','is_deleted':True}]}]}}
    total,groups,articles=parse_publish_page(data)
    assert groups==['123'] and len(articles)==1
    assert articles[0]['url'] and articles[0]['publish_status']=='已删除'
    assert articles[0]['date']=='2021-11-23'

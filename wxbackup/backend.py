"""Backend page discovery, including server-rendered publication lists."""
from __future__ import annotations

from urllib.parse import urlsplit, parse_qs

from .model import BackupError, parse_publish_page


BOOTSTRAP_JS = r'''() => {
 const seen=new Set();
 function visit(v,depth) {
   if(depth>5 || v==null) return null;
   if(typeof v==='string') {
     if(!/^[\s]*[\[{]/.test(v)) return null;
     try {return visit(JSON.parse(v),depth+1);} catch {return null;}
   }
   if(typeof v!=='object' || seen.has(v)) return null;
   seen.add(v);
   if(Object.prototype.hasOwnProperty.call(v,'publish_page')) return {publish_page:v.publish_page,base_resp:v.base_resp||{ret:0}};
   if(Array.isArray(v.publish_list)) return {publish_page:v};
   for(const [k,x] of Object.entries(v)) {
     if(/token|cookie|key|ticket|password/i.test(k)) continue;
     if(typeof x==='object' || typeof x==='string') {const found=visit(x,depth+1); if(found) return found;}
   }
   return null;
 }
 for(const root of [window.wx?.cgiData,window.cgiData,window.cgi_data,window.__INITIAL_STATE__]) {
   const found=visit(root,0); if(found) return found;
 }
 return null;
}'''


def logged_in_page(context, preferred=None):
    pages=[page for page in context.pages if not page.is_closed()]
    candidates=[]
    for page in pages:
        parts=urlsplit(page.url)
        if parts.hostname=='mp.weixin.qq.com' and parse_qs(parts.query).get('token'):
            candidates.append(page)
    publications=[p for p in candidates if urlsplit(p.url).path.endswith('/appmsgpublish')]
    if publications: return publications[-1]
    if preferred in candidates: return preferred
    if candidates: return candidates[-1]
    raise BackupError('未发现已登录的后台标签页。请在本程序打开的 Edge 中登录后重试。')


def bootstrap(page):
    value=page.evaluate(BOOTSTRAP_JS)
    if value is not None: parse_publish_page(value)
    return value


def check_unfiltered(url):
    query=parse_qs(urlsplit(url).query,keep_blank_values=True)
    if any(query.get(k,[''])[0] not in ('','0','null') for k in ('query','fakeid','start_time','end_time')):
        raise BackupError('检测到搜索、日期或其他账号筛选，请清空后再采集本账号全部发表记录。')


class ResponseTracker:
    """Listen from browser launch, rather than only during the collect button."""
    def __init__(self):
        self.responses=[]
        self.notes=[]

    def capture(self,response):
        parts=urlsplit(response.url)
        if parts.hostname!='mp.weixin.qq.com' or not parts.path.startswith('/cgi-bin/'):
            return
        if not any(name in parts.path for name in ('appmsgpublish','masssend')):
            return
        note={'path':parts.path,'query_fields':sorted(parse_qs(parts.query)),
              'method':response.request.method,'http_status':response.status,
              'content_type':response.headers.get('content-type','')}
        try:
            data=response.json()
            note['response_fields']=list(data) if isinstance(data,dict) else [type(data).__name__]
            if isinstance(data,dict) and 'publish_page' in data:
                try:
                    parse_publish_page(data)
                    self.responses.append((response.url,response.request.method))
                    self.responses=self.responses[-30:]
                except Exception as exc:
                    note['parse_error']=str(exc)
        except Exception:
            note['response_kind']='HTML/非JSON，尝试页面内置数据'
        self.notes.append(note)
        self.notes=self.notes[-50:]


def diagnostic(context,tracker):
    pages=[]
    for page in context.pages:
        if page.is_closed(): continue
        parts=urlsplit(page.url)
        if parts.hostname!='mp.weixin.qq.com': continue
        item={'path':parts.path,'query_fields':sorted(parse_qs(parts.query))}
        try:
            item['bootstrap_fields']=page.evaluate('''() => {
              const result={};
              const roots={wx_cgiData:window.wx?.cgiData,cgiData:window.cgiData,cgi_data:window.cgi_data,initial:window.__INITIAL_STATE__};
              for(const [key,value] of Object.entries(roots)) {
                if(value && typeof value==='object') result[key]=Object.keys(value).filter(k=>!/token|cookie|key|ticket|password/i.test(k));
              }
              return result;
            }''')
        except Exception: item['page_state']='页面已关闭或正在跳转'
        pages.append(item)
    return {'pages':pages,'list_responses':tracker.notes if tracker else [],
            'privacy':'只记录路径、字段名和错误，不记录 token、Cookie 或完整后台地址'}

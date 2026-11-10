from __future__ import annotations

import base64
import hashlib
import html
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .model import BackupError, Cancelled, atomic_json


# Copy computed article styles, avoiding dependencies on WeChat's stylesheets.
SNAPSHOT_JS = r'''() => {
 const root = document.querySelector('#js_article') || document.querySelector('.rich_media_area_primary') || document.querySelector('#js_content');
 if (!root || !document.querySelector('#js_content')) throw Error('没有找到文章正文');
 const copy = root.cloneNode(true);
 const originals=[root,...root.querySelectorAll('*')];
 const clones=[copy,...copy.querySelectorAll('*')];
 const props=['display','visibility','opacity','color','background-color','background-image','background-size','background-position','background-repeat',
 'font-family','font-size','font-weight','font-style','line-height','letter-spacing','word-spacing','text-align','text-indent','text-decoration',
 'white-space','word-break','overflow-wrap','vertical-align','border-collapse','border-spacing','table-layout','list-style-type','list-style-position',
 'margin-top','margin-right','margin-bottom','margin-left','padding-top','padding-right','padding-bottom','padding-left',
 'border-top','border-right','border-bottom','border-left','border-radius','box-sizing','float','clear','max-width','min-width','height',
 'flex-direction','align-items','justify-content','gap','grid-template-columns','transform','transform-origin'];
 for(let i=0;i<originals.length;i++) {
   const el=originals[i], clone=clones[i], cs=getComputedStyle(el);
   if (!(clone instanceof HTMLElement) && !(clone instanceof SVGElement)) continue;
   clone.setAttribute('style',props.map(p=>p+':'+cs.getPropertyValue(p)).join(';'));
   // Fix table column widths while allowing long articles to flow on A4.
   if(['TD','TH','TABLE'].includes(el.tagName)) clone.style.width=cs.width;
   if(el.tagName==='IMG') {
      clone.setAttribute('src',el.getAttribute('data-src') || el.currentSrc || el.src);
      clone.style.maxWidth='100%'; clone.style.height='auto';
      clone.removeAttribute('srcset'); clone.removeAttribute('sizes'); clone.removeAttribute('loading');
   }
 }
 copy.style.maxWidth='760px'; copy.style.margin='0 auto'; copy.style.height='auto';
 const content=copy.id==='js_content'?copy:copy.querySelector('#js_content');
 content.style.visibility='visible'; content.style.opacity='1'; content.style.height='auto';
 return copy.outerHTML;
}'''

CSS_URL = re.compile(r'url\(\s*[\'"]?([^\)\'\"]+)[\'"]?\s*\)', re.I)
TRANSPARENT='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/h9sAAAAASUVORK5CYII='


def file_record(path):
    return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'size':path.stat().st_size}


def valid_file(path, record):
    return bool(record and path.is_file() and record.get('size')==path.stat().st_size and record.get('sha256')==hashlib.sha256(path.read_bytes()).hexdigest())


class Downloader:
    def __init__(self, playwright, log=print, progress=lambda *x: None, checkpoint=lambda: None):
        self.playwright=playwright; self.log=log; self.progress=progress; self.checkpoint=checkpoint

    def wait(self, page, seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            self.checkpoint(); page.wait_for_timeout(150)

    def resource(self, context, url, referer):
        for attempt in range(3):
            self.checkpoint()
            try:
                response=context.request.get(url,headers={'Referer':referer},timeout=30000)
                try:
                    mime=response.headers.get('content-type','').split(';')[0].lower()
                    if not response.ok or not mime.startswith('image/'):
                        raise BackupError(f'图片响应异常 HTTP {response.status} / {mime}')
                    body=response.body()
                    if not body: raise BackupError('图片内容为空')
                    if len(body)>40*1024*1024: raise BackupError('单张图片超过40MB限制')
                    return 'data:'+mime+';base64,'+base64.b64encode(body).decode('ascii')
                finally:
                    response.dispose()
            except Cancelled: raise
            except Exception:
                if attempt==2: raise BackupError('图片下载失败（三次尝试）')
                self.wait(self.page,attempt+1)

    def offline_html(self, fragment, article, context):
        soup=BeautifulSoup(fragment,'html.parser'); warnings=[]; cache={}
        for node in soup.select('script,iframe,video,audio,mpvoice,mpvideo,mp-common-videosnap,mp-common-mpaudio,object,embed,form,link,base,meta'):
            if node.name in ('iframe','video','audio','mpvoice','mpvideo','mp-common-videosnap','mp-common-mpaudio','object','embed'):
                warnings.append('正文包含视频/音频/嵌入内容，未离线保存，需人工核对')
            node.decompose()
        def localize(value):
            value=str(value).strip()
            if value.startswith('data:image/'): return value
            if value.startswith('#'): return value
            url=urljoin(article['url'],value)
            if urlsplit(url).scheme not in ('https','http'): return TRANSPARENT
            if url not in cache:
                try: cache[url]=self.resource(context,url,article['url'])
                except Cancelled: raise
                except Exception:
                    warnings.append('图片未保存：'+url)
                    cache[url]=TRANSPARENT
            return cache[url]
        for node in soup.find_all(True):
            self.checkpoint()
            for attr in list(node.attrs):
                if attr.lower().startswith('on') or attr in ('srcset','data-src','data-srcset','data-backsrc','data-original','data-lazy-src','ping','nonce','integrity','contenteditable'):
                    del node.attrs[attr]
            if node.name in ('img','image'):
                attr='src' if node.name=='img' else 'href'
                value=node.get(attr) or node.get('xlink:href')
                if value: node[attr]=localize(value)
                node.attrs.pop('xlink:href',None)
            if node.has_attr('style'):
                node['style']=CSS_URL.sub(lambda m:'url("'+localize(m.group(1))+'")',node['style'])
            if node.name=='style':
                # Snapshot contains inline computed styles; stale styles can import remote resources.
                node.string=''
            if node.has_attr('href') and node.name not in ('image',):
                value=urljoin(article['url'],str(node['href']))
                if urlsplit(value).scheme in ('http','https'):
                    node['href']=value; node['rel']='noreferrer noopener'
                else: node.attrs.pop('href',None)
            for attr in ('src','poster','background'):
                if node.has_attr(attr) and not (node.name=='img' and attr=='src'):
                    node[attr]=localize(node[attr])
        title=html.escape(article['title']); url=html.escape(article['url'],quote=True)
        document=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>body{{margin:24px;background:white;color:#222;font-family:'Microsoft YaHei',sans-serif;}}
img,svg{{max-width:100%;}}*{{-webkit-print-color-adjust:exact;print-color-adjust:exact;}}table{{max-width:100%;}}pre{{white-space:pre-wrap;}}
.backup-meta{{max-width:760px;margin:0 auto 24px;color:#666;font-size:13px;overflow-wrap:anywhere;}}
@page{{size:A4;margin:12mm;}}</style></head><body>
<div class="backup-meta">本地备份 · {html.escape(article['date'])} · <a href="{url}">原文链接（联网访问）</a></div>
{soup}</body></html>'''
        return document, sorted(set(warnings))

    def capture(self, article, context):
        page=self.page
        response=page.goto(article['url'],wait_until='domcontentloaded',timeout=45000)
        if response and response.status>=400: raise BackupError(f'文章 HTTP {response.status}')
        try:
            page.locator('#js_content').wait_for(state='attached',timeout=20000)
        except Exception as exc:
            text=page.locator('body').inner_text(timeout=5000)
            reasons=[s for s in ('该内容已被发布者删除','此内容已被删除','该内容暂时无法查看','此内容因违规无法查看','环境异常','验证','内容不存在','发送失败') if s in text]
            raise BackupError('无法读取正文：'+(' / '.join(reasons) if reasons else '未发现正文节点（可能需要验证或页面已变化）')) from exc
        page.evaluate("() => { const e=document.querySelector('#js_content'); e.style.visibility='visible'; e.style.opacity='1'; }")
        # Trigger lazy images without waiting forever for trackers or long-polling requests.
        height=page.evaluate('document.documentElement.scrollHeight')
        for y in range(0,min(height,200000),900):
            self.checkpoint(); page.evaluate('(y)=>window.scrollTo(0,y)',y); self.wait(page,.08)
        page.evaluate('window.scrollTo(0,0)'); self.wait(page,.5)
        if not page.locator('#js_content').inner_text().strip() and page.locator('#js_content img').count()==0:
            raise BackupError('正文为空，未标记为备份成功。')
        return self.offline_html(page.evaluate(SNAPSHOT_JS),article,context)

    def save_pdf(self, document, path, context):
        pdf_page=context.new_page()
        try:
            # No network access during rendering: an offline artifact must stand on its own.
            pdf_page.route('**/*',lambda route:route.abort())
            pdf_page.set_content(document,wait_until='load',timeout=45000)
            pdf_page.evaluate('async()=>{await document.fonts.ready; await Promise.all([...document.images].map(i=>i.decode().catch(()=>{})));}')
            pdf_page.emulate_media(media='screen')
            temp=path.with_suffix('.pdf.tmp')
            pdf_page.pdf(path=str(temp),format='A4',print_background=True,prefer_css_page_size=True)
            os.replace(temp,path)
        finally: pdf_page.close()

    def run(self, store, formats):
        if not store.data.get('collection',{}).get('complete'):
            raise BackupError('请先完成并核对全部文章列表，再开始批量下载。')
        if not formats or set(formats)-{'html','pdf'}: raise BackupError('请选择 HTML 或 PDF 格式。')
        self.browser=self.playwright.chromium.launch(channel='msedge',headless=True)
        context=self.browser.new_context(viewport={'width':1000,'height':900},locale='zh-CN')
        self.page=context.new_page(); total=len(store.data['articles'])
        store.data['requested_formats']=list(formats)
        try:
            for index,article in enumerate(store.data['articles'],1):
                self.checkpoint(); folder=store.folder(article)
                files=article.setdefault('files',{})
                needed=[fmt for fmt in formats if not valid_file(folder/f'article.{fmt}',files.get(fmt)) or article.get('warnings')]
                if not needed:
                    article['download_status']='已完成（校验通过）'; article['error']=''
                elif article['publish_status']=='已删除' or not article['url']:
                    article['download_status']='已删除/无链接'; article['error']='后台无可用原文，无法恢复正文'
                else:
                    article['download_status']='下载中'; article['error']=''; store.save()
                    for attempt in range(3):
                        try:
                            self.checkpoint()
                            document,warnings=self.capture(article,context)
                            article['warnings']=warnings; folder.mkdir(parents=True,exist_ok=True)
                            if 'html' in needed:
                                path=folder/'article.html'; temp=folder/'article.html.tmp'
                                temp.write_text(document,encoding='utf-8'); os.replace(temp,path)
                                files['html']=file_record(path)
                                store.save()
                            if 'pdf' in needed:
                                path=folder/'article.pdf'; self.save_pdf(document,path,context)
                                files['pdf']=file_record(path)
                                store.save()
                            article['download_status']='部分完成（需核对资源）' if warnings else '已完成'
                            article['error']=''
                            break
                        except Cancelled: raise
                        except Exception as exc:
                            article['error']=re.sub(r'https?://\S+','[链接已隐藏]',str(exc))[:1500]
                            article['download_status']='失败'
                            if attempt<2:
                                self.log(f'文章 {index}/{total} 失败，准备第 {attempt+2} 次尝试')
                                self.wait(self.page,3*(attempt+1))
                    self.wait(self.page,1.5)
                store.save()
                self.log(f'{index}/{total} · {article["title"]} · {article["download_status"]}')
                self.progress(index,total,f'下载 {index}/{total} · {article["download_status"]}')
                if index%10==0:
                    from .report import export_reports
                    try: export_reports(store)
                    except PermissionError: self.log('Excel 目录被占用，最终将再次尝试导出。')
        finally:
            for article in store.data['articles']:
                if article['download_status']=='下载中': article['download_status']='待继续'
            store.save(); self.browser.close()

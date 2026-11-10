from __future__ import annotations

import os
from collections import Counter
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

from .model import atomic_json


def export_reports(store):
    articles=store.data['articles']; meta=store.data.get('collection',{})
    book=Workbook(); sheet=book.active; sheet.title='文章目录'
    sheet.append(['完整标题','发表日期（北京时间）','原文链接','发表状态','下载状态','HTML路径','PDF路径','图片/其他警告','错误','备注','发表记录ID'])
    for a in articles:
        folder=store.folder(a)
        values=[a['title'],a['date'],a['url'],a['publish_status'],a['download_status'],
            str(folder/'article.html') if a.get('files',{}).get('html') else '',
            str(folder/'article.pdf') if a.get('files',{}).get('pdf') else '',
            '; '.join(a.get('warnings',[])),a.get('error',''),
            '; '.join(filter(None,[a.get('date_note'),a.get('metadata_note')])), ','.join(a['group_ids'])]
        sheet.append(values)
        # Explicit string cells prevent titles beginning with =, +, - or @ becoming formulas.
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value,str): cell.data_type='s'
    sheet.freeze_panes='A2'; sheet.auto_filter.ref=sheet.dimensions
    widths=[55,24,55,20,22,65,65,65,60,50,35]
    for i,width in enumerate(widths,1): sheet.column_dimensions[sheet.cell(1,i).column_letter].width=width
    for cell in sheet[1]:
        cell.font=Font(bold=True,color='FFFFFF'); cell.fill=PatternFill('solid',fgColor='166534')
    for row in sheet.iter_rows(min_row=2):
        for cell in row: cell.alignment=Alignment(vertical='top',wrap_text=True)
    stats=Counter(a['download_status'] for a in articles)
    report={'生成时间':datetime.now().isoformat(timespec='seconds'),'列表完整核对':bool(meta.get('complete')),
            '后台发表次数':meta.get('expected_publications'),'已核对发表次数':meta.get('collected_publications',0),
            '已采集页数':meta.get('pages',0),'去重后文章及异常记录数':len(articles),'下载状态':dict(stats),
            '已删除记录数':sum(a['publish_status']=='已删除' for a in articles),
            '缺少链接记录数':sum(not a['url'] for a in articles),
            '元数据待核对记录数':sum(bool(a.get('date_note') or a.get('metadata_note')) for a in articles),
            '采集错误':meta.get('error',''),
            '说明':'发表次数不等于文章篇数；空发表记录保留为异常行，其历史文章数量无法推断。视频、音频及互动内容需人工核对。'}
    summary=book.create_sheet('核对统计')
    for k,v in report.items(): summary.append([k,str(v)])
    summary.column_dimensions['A'].width=30; summary.column_dimensions['B'].width=100
    temporary=store.root/'文章目录.tmp.xlsx'
    book.save(temporary); os.replace(temporary,store.root/'文章目录.xlsx')
    atomic_json(store.root/'备份统计.json',report)
    (store.root/'备份统计.txt').write_text('\n'.join(f'{k}：{v}' for k,v in report.items()),encoding='utf-8')
    atomic_json(store.root/'异常记录.json',[a for a in articles if a.get('error') or a.get('warnings') or a['publish_status']!='已发表' or a.get('date_note') or a.get('metadata_note')])

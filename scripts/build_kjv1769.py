#!/usr/bin/env python3
"""Build an additive, text-only SOTW KJV1769 static Bible library from a byte-locked eBible USFM ZIP.

No Strong's numbers or original-language alignment records are emitted. The source ZIP is never copied
into the publication tree because it contains embedded Strong's annotations. No external dependencies.
"""
import collections
import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path

SOURCE = Path('/mnt/data/eng-kjv2006_usfm.zip')
BASE = Path('/mnt/data/kjv_work/SOTW_KJV1769_REPOSITORY_ROOT')
OUT = Path('/mnt/data/kjv_work/release')
EDITION = 'KJV1769'
TODAY = '2026-11-09'
SOURCE_URL = 'https://ebible.org/Scriptures/details.php?id=eng-kjv2006'
SOURCE_ZIP_URL = 'https://ebible.org/Scriptures/eng-kjv2006_usfm.zip'

BOOKS = [
('GEN','Genesis','genesis'),('EXO','Exodus','exodus'),('LEV','Leviticus','leviticus'),('NUM','Numbers','numbers'),('DEU','Deuteronomy','deuteronomy'),
('JOS','Joshua','joshua'),('JDG','Judges','judges'),('RUT','Ruth','ruth'),('1SA','1 Samuel','first-samuel'),('2SA','2 Samuel','second-samuel'),
('1KI','1 Kings','first-kings'),('2KI','2 Kings','second-kings'),('1CH','1 Chronicles','first-chronicles'),('2CH','2 Chronicles','second-chronicles'),
('EZR','Ezra','ezra'),('NEH','Nehemiah','nehemiah'),('EST','Esther','esther'),('JOB','Job','job'),('PSA','Psalms','psalms'),('PRO','Proverbs','proverbs'),
('ECC','Ecclesiastes','ecclesiastes'),('SNG','Song of Solomon','song-of-solomon'),('ISA','Isaiah','isaiah'),('JER','Jeremiah','jeremiah'),
('LAM','Lamentations','lamentations'),('EZK','Ezekiel','ezekiel'),('DAN','Daniel','daniel'),('HOS','Hosea','hosea'),('JOL','Joel','joel'),('AMO','Amos','amos'),
('OBA','Obadiah','obadiah'),('JON','Jonah','jonah'),('MIC','Micah','micah'),('NAM','Nahum','nahum'),('HAB','Habakkuk','habakkuk'),
('ZEP','Zephaniah','zephaniah'),('HAG','Haggai','haggai'),('ZEC','Zechariah','zechariah'),('MAL','Malachi','malachi'),
('MAT','Matthew','matthew'),('MRK','Mark','mark'),('LUK','Luke','luke'),('JHN','John','john'),('ACT','Acts','acts'),('ROM','Romans','romans'),
('1CO','1 Corinthians','first-corinthians'),('2CO','2 Corinthians','second-corinthians'),('GAL','Galatians','galatians'),('EPH','Ephesians','ephesians'),
('PHP','Philippians','philippians'),('COL','Colossians','colossians'),('1TH','1 Thessalonians','first-thessalonians'),
('2TH','2 Thessalonians','second-thessalonians'),('1TI','1 Timothy','first-timothy'),('2TI','2 Timothy','second-timothy'),
('TIT','Titus','titus'),('PHM','Philemon','philemon'),('HEB','Hebrews','hebrews'),('JAS','James','james'),
('1PE','1 Peter','first-peter'),('2PE','2 Peter','second-peter'),('1JN','1 John','first-john'),('2JN','2 John','second-john'),
('3JN','3 John','third-john'),('JUD','Jude','jude'),('REV','Revelation','revelation')]

# Source uses \w and nested \+w tags, mostly in the divine-name \nd markup.
W_TAG = re.compile(r'\\\+?w\s+([^|\\]*?)\|[^\\]*?\\\+?w\*')
FOOTNOTE = re.compile(r'\\f\s+\+.*?\\f\*', re.DOTALL)
CHAR_TAG = re.compile(r'\\\+?(?:nd|wj|tl)\*?')
ADD_TAG = re.compile(r'(\\\+?add\*?)')
USFM_LINE = re.compile(r'^\\([a-z0-9]+)(?:\s+|$)(.*)$')
REMAINING_MARKER = re.compile(r'\\[A-Za-z+]')


def h(b): return hashlib.sha256(b).hexdigest()

def dumps(o): return json.dumps(o, ensure_ascii=False, indent=2) + '\n'

def write(rel, content):
    p = BASE / rel; p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(content if isinstance(content,bytes) else content.encode('utf-8'))

def jwrite(rel, obj): write(rel, dumps(obj))

def simplify(raw):
    """Remove lexical/typographic USFM wrappers, retaining printed English words and punctuation."""
    starts = len(re.findall(r'\\\+?w\s+',raw))
    raw, n = W_TAG.subn(lambda m: m.group(1), raw)
    if starts != n: raise ValueError(f'Unmatched USFM word tags: {starts} starts vs {n} matched in {raw[:150]}')
    raw = CHAR_TAG.sub('',raw)
    if REMAINING_MARKER.search(re.sub(r'\\\+?add\*?', '', raw)): raise ValueError(f'Unexpected unresolved USFM marker in {raw[:150]}')
    return raw

def strip_notes(raw):
    found=FOOTNOTE.findall(raw)
    if len(found)!=len(re.findall(r'\\f\s+\+',raw)):
        raise ValueError('Unmatched USFM translator note')
    return FOOTNOTE.sub('',raw),found

def text_spans(raw):
    raw=simplify(raw)
    pieces=[]; italic=False
    for chunk in ADD_TAG.split(raw):
        if chunk in ('\\add', '\\+add'):
            if italic: raise ValueError('Nested supplied-word marker')
            italic=True; continue
        if chunk in ('\\add*', '\\+add*'):
            if not italic: raise ValueError('Unmatched supplied-word closer')
            italic=False;continue
        if not chunk: continue
        txt=re.sub(r'\s+',' ',chunk)
        if not txt:continue
        kind='supplied' if italic else 'text'
        if pieces and pieces[-1]['kind']==kind: pieces[-1]['text']+=txt
        else: pieces.append({'text':txt,'kind':kind})
    if italic: raise ValueError('Unclosed supplied-word span')
    if not pieces: raise ValueError('Empty verse text')
    pieces[0]['text']=pieces[0]['text'].lstrip()
    pieces[-1]['text']=pieces[-1]['text'].rstrip()
    # USFM char markers can carry whitespace on *both* sides of a supplied run.
    # Preserve italic boundaries but prevent doubled spaces in rendered Scripture.
    cleaned=[]
    for piece in pieces:
        if not piece['text']:continue
        if cleaned and cleaned[-1]['text'].endswith(' ') and piece['text'].startswith(' '):
            piece['text']=piece['text'].lstrip(' ')
        if not piece['text']:continue
        if cleaned and cleaned[-1]['kind']==piece['kind']:
            cleaned[-1]['text']+=piece['text']
        else:cleaned.append(piece)
    if cleaned:
        cleaned[0]['text']=cleaned[0]['text'].lstrip()
        cleaned[-1]['text']=cleaned[-1]['text'].rstrip()
    return [x for x in cleaned if x['text']]

def nonverse_text(raw):
    # Psalm superscriptions and original edition headings can contain Strong's markup.
    s,_=strip_notes(raw)
    s=simplify(ADD_TAG.sub('',s))
    return re.sub(r'\s+',' ',s).strip()

def note_text(raw):
    raw=re.sub(r'^\\f\s+\+','',raw);raw=re.sub(r'\\f\*$','',raw)
    raw=re.sub(r'\\fr\s+[^\\]+','',raw)
    raw=re.sub(r'\\ft\s+','',raw)
    raw=re.sub(r'\\[a-zA-Z0-9+]+\*?\s*','',raw)
    return re.sub(r'\s+',' ',raw).strip()

def chapter_from_source(source, code):
    chapters=collections.OrderedDict()
    extras=collections.defaultdict(lambda:{'superscriptions':[],'source_section_headings':[]})
    footnotes=collections.defaultdict(list)
    pending_paragraph=True; current=None; chapter=None; saw_word=0; saw_note=0; supplied=0
    for line in source.splitlines():
        line=line.strip()
        if not line:continue
        m=USFM_LINE.match(line)
        if not m: raise ValueError(f'Unknown line {code}: {line[:120]}')
        marker,rest=m.groups()
        if marker=='c':
            chapter=int(rest.strip());
            if chapter in chapters: raise ValueError(f'duplicate chapter {code}.{chapter}')
            chapters[chapter]=[]; current=None;pending_paragraph=True
        elif marker=='v':
            if chapter is None:raise ValueError('verse before chapter')
            mm=re.match(r'(\d+)(?:\s+|$)(.*)',rest,re.DOTALL)
            if not mm:raise ValueError('Malformed verse '+rest[:30])
            verse=int(mm.group(1));content=mm.group(2)
            no_note,fs=strip_notes(content)
            spans=text_spans(no_note)
            key=f'{code}.{chapter}.{verse}'
            current={'id':key,'edition_verse_id':f'{EDITION}:{key}','verse':verse,
                     'spans':spans,'paragraph_start':pending_paragraph}
            chapters[chapter].append(current)
            pending_paragraph=False
            supplied+=sum(x['kind']=='supplied' for x in spans)
            saw_word+=len(re.findall(r'\\\+?w\s+',content))
            saw_note+=len(fs)
            for foot in fs:
                footnotes[chapter].append({'id':key,'text':note_text(foot)})
        elif marker in ('p','q1'):
            if marker=='p':pending_paragraph=True
            if rest.strip():
                if current is None: raise ValueError(f'Content before verse on {code}.{chapter}: {line[:100]}')
                raw,fs=strip_notes(rest)
                s=text_spans(raw)
                # Appended poetry lines are not found in this release, but handle them conservatively.
                current['spans'][-1]['text']+=' '
                current['spans'].extend(s)
                for foot in fs: footnotes[chapter].append({'id':current['id'],'text':note_text(foot)})
        elif marker in ('d','s1'):
            if chapter is None: raise ValueError('intro before chapter')
            tx=nonverse_text(rest)
            if tx:extras[chapter]['superscriptions' if marker=='d' else 'source_section_headings'].append(tx)
        elif marker in ('b','id','h','toc1','toc2','toc3','mt1','mt2'):
            continue
        else: raise ValueError(f'Unexpected line type: {code} {marker}')
    return chapters,extras,footnotes,{'source_word_tags_removed':saw_word,'source_footnote_markers_removed':saw_note,'supplied_spans':supplied}

# Identity/provenance alone; do not include third-party source USFM (it contains Strong's tags).
CSS = '''
:root{font-family:Georgia,'Times New Roman',serif;color:#192b32;background:#f7f5ef}
*{box-sizing:border-box}body{margin:0}header{background:#132f37;color:#fcf8ec;padding:20px max(20px,calc((100vw - 1080px)/2))}
header small{color:#c8d7d1;letter-spacing:.11em;font:600 11px Arial,sans-serif}
header h1{font-weight:normal;font-size:clamp(25px,4vw,38px);margin:6px 0}
main{max-width:1080px;margin:24px auto;padding:0 16px}
.panel{background:#fff;border:1px solid #d4d9d6;box-shadow:0 2px 16px #0b28350a;border-radius:12px;min-width:0;overflow:hidden}
.toolbar{padding:15px;border-bottom:1px solid #e4e6e2;display:flex;gap:9px;align-items:center;flex-wrap:wrap}
.toolbar label{font:600 13px Arial,sans-serif;color:#304f58}
select,button{font:14px Arial,sans-serif;border:1px solid #a8b4b6;border-radius:6px;padding:9px;background:#fff;color:#173943;max-width:100%}
button{background:#1c515a;color:#fff;border-color:#1c515a;cursor:pointer}
button:disabled{opacity:.4;cursor:default}
button:focus-visible,select:focus-visible,a:focus-visible,.verse:focus-visible{outline:3px solid #b48f47;outline-offset:2px}
#title{margin:0 0 12px;font-size:clamp(24px,4vw,32px);font-weight:normal}
#text{padding:18px clamp(14px,4vw,34px) 26px;font-size:clamp(18px,2vw,21px);line-height:1.8}
.verse{display:inline;cursor:pointer;border-radius:4px;padding:2px 1px;outline-offset:0}
.verse:focus{outline:2px solid #b48f47}
.verse.selected{background:#eff4ed;box-shadow:0 0 0 2px #96b2a3}
.vnum{font:600 12px Arial,sans-serif;color:#51767c;vertical-align:super;margin-right:3px}
.verse.paragraph::before{content:'';display:block;height:.9em}
.supplied{font-style:italic}
.superscription{font:italic 15px/1.65 Georgia,serif;color:#557078;margin:8px 0 16px}
#selection{padding:16px;background:#f7faf7;border-top:1px solid #dce6df;font:14px/1.6 Arial,sans-serif}
#selection strong{color:#1d414a}
#error{color:#9c3933;padding:0 16px;font:14px Arial,sans-serif}
.tools-note{font:13px/1.6 Arial,sans-serif;color:#60777b;margin:4px 0 0}
.about{margin:24px 0;font:14px/1.65 Arial,sans-serif;color:#2c5058}
.about summary{cursor:pointer;font-weight:700}.about a,a{color:#1a5562}footer{max-width:1080px;margin:0 auto 32px;padding:0 16px;font:12px/1.6 Arial,sans-serif;color:#577078}
.navrow{display:flex;gap:8px;flex-wrap:wrap;align-items:center;justify-content:space-between}
@media(max-width:620px){.toolbar{align-items:flex-end}.toolbar select{min-width:100px}header{padding:18px 16px}#text{line-height:1.75}}
'''

JS = r'''(()=>{
'use strict';
const root=document.documentElement;
const code=root.dataset.book;
const dataBase='../../../data/kjv1769/';
const $=id=>document.getElementById(id);
let book=null,chapter=null,selectedVerse=1,bookList=[];
function setError(s){$('error').textContent=s||'';}
function urlFor(ch,v){return '#'+code+'.'+ch+'.'+v;}
function selectedFromLocation(){
 const hash=decodeURIComponent(location.hash.replace(/^#/,''));
 const match=hash.match(/^([A-Z0-9]{3})\.(\d+)\.(\d+)$/);
 if(match && match[1]===code)return [Number(match[2]),Number(match[3])];
 const q=new URLSearchParams(location.search);const ref=q.get('ref');
 const m=ref&&ref.match(/^([A-Z0-9]{3})\.(\d+)\.(\d+)$/);
 if(m && m[1]===code)return [Number(m[2]),Number(m[3])];
 return [1,1];
}
async function json(path){let r=await fetch(path,{cache:'no-cache'});if(!r.ok)throw new Error('Unable to load '+path+' (HTTP '+r.status+')');return r.json();}
function makeOption(value,label){const o=document.createElement('option');o.value=String(value);o.textContent=label;return o;}
async function init(){
 try{
 const [books,catalog]=await Promise.all([json(dataBase+'books.json'),json(dataBase+'catalog-'+root.dataset.slug+'.json')]);
 bookList=books.books;book=catalog;
 $('bookName').textContent=book.book_name;
 $('title').textContent=book.book_name;
 $('bookSelect').replaceChildren(...bookList.map(b=>makeOption(b.code,b.name)));
 $('bookSelect').value=code;
 $('chapterSelect').replaceChildren(...Array.from({length:book.chapter_count},(_,i)=>makeOption(i+1,'Chapter '+(i+1))));
 $('bookSelect').addEventListener('change',()=>{
   const b=bookList.find(x=>x.code===$('bookSelect').value);
   if(b)location.href='../../../books/'+b.slug+'/site/index.html#'+b.code+'.1.1';
 });
 $('chapterSelect').addEventListener('change',()=>load(Number($('chapterSelect').value),1));
 $('verseSelect').addEventListener('change',()=>select(Number($('verseSelect').value),true));
 $('prev').addEventListener('click',()=>load(Number($('chapterSelect').value)-1,1));
 $('next').addEventListener('click',()=>load(Number($('chapterSelect').value)+1,1));
 $('copy').addEventListener('click',()=>navigator.clipboard?.writeText(location.href));
 window.addEventListener('hashchange',()=>{const [ch,v]=selectedFromLocation(); if(ch!==chapter?.chapter)load(ch,v);else select(v,false);});
 const [ch,v]=selectedFromLocation();await load(ch,v);
 }catch(e){setError(e.message);}
}
async function load(ch,v){
 if(!book){return;}
 if(ch<1||ch>book.chapter_count){setError('That chapter is outside this book.');return;}
 try{
  setError(''); const path=dataBase+root.dataset.slug+'/chapters/'+String(ch).padStart(2,'0')+'.json';
  const [data,heads]=await Promise.all([json(path),json(dataBase+root.dataset.slug+'/chapter-extras.json')]);
  if(data.book_code!==code||data.edition_id!=='KJV1769'||data.chapter!==ch)throw new Error('Chapter identity mismatch');
  chapter=data;
  $('chapterSelect').value=String(ch);
  $('prev').disabled=ch<=1;$('next').disabled=ch>=book.chapter_count;
  $('verseSelect').replaceChildren(...data.verses.map(x=>makeOption(x.verse,'Verse '+x.verse)));
  $('title').textContent=book.book_name+' · Chapter '+ch;
  const verses=document.createDocumentFragment();
  const extra=heads.chapters[String(ch)];
  if(extra?.superscriptions?.length){const p=document.createElement('p');p.className='superscription';p.textContent=extra.superscriptions.join(' ');verses.append(p);}
  for(const vrow of data.verses){
   const el=document.createElement('span');el.className='verse'+(vrow.paragraph_start?' paragraph':'');el.id=vrow.id;el.tabIndex=0;el.setAttribute('role','button');el.setAttribute('aria-label',book.book_name+' '+ch+':'+vrow.verse);
   const num=document.createElement('span');num.className='vnum';num.textContent=String(vrow.verse);el.append(num);
   for(const sp of vrow.spans){const n=document.createElement('span');if(sp.kind==='supplied')n.className='supplied';n.textContent=sp.text;el.append(n);}
   el.append(document.createTextNode(' '));
   el.addEventListener('click',()=>select(vrow.verse,true));
   el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(vrow.verse,true);}});
   verses.append(el);
  }
  $('text').replaceChildren(verses);
  select(v,true);
 }catch(e){setError(e.message);$('text').textContent='';}
}
function select(n,updateHash){
 if(!chapter)return;
 let row=chapter.verses.find(v=>v.verse===n)||chapter.verses[0];
 if(!row)return;
 selectedVerse=row.verse;
 $('verseSelect').value=String(selectedVerse);
 $('selectionRef').textContent=book.book_name+' '+chapter.chapter+':'+selectedVerse;
 $('selectionId').textContent=row.id;
 document.querySelectorAll('.verse.selected').forEach(el=>el.classList.remove('selected'));
 const el=document.getElementById(row.id);if(el)el.classList.add('selected');
 if(updateHash && location.hash!==urlFor(chapter.chapter,selectedVerse)) history.replaceState(null,'',urlFor(chapter.chapter,selectedVerse));
}
init();
})();
'''

PAGE = '''<!doctype html><html lang="en" data-book="{code}" data-slug="{slug}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Servants of the Way | KJV {name}</title><link rel="stylesheet" href="../../../assets/kjv1769/reader.css"></head>
<body><header><small>SERVANTS OF THE WAY · BIBLE FOUNDATION</small><h1>King James Version · 1769</h1><div><span id="bookName">{name}</span> · Scripture text</div></header>
<main><section class="panel"><div class="toolbar"><label for="bookSelect">Book</label><select id="bookSelect" aria-label="Select Bible book"></select><label for="chapterSelect">Chapter</label><select id="chapterSelect"></select><label for="verseSelect">Verse</label><select id="verseSelect"></select><button id="prev">Previous chapter</button><button id="next">Next chapter</button></div>
<h2 id="title" style="padding:12px 20px 0">{name}</h2><div id="text" aria-live="polite"><p>Loading chapter…</p></div><p id="error" role="alert"></p><div id="selection"><strong id="selectionRef">Select a verse</strong> <span>· Reference ID: <code id="selectionId"></code></span> <button id="copy">Copy verse link</button>
<p class="tools-note">Verse identifiers are ready for the separate original-language and historical-commentary libraries. Study panels and word-click integration are not included in this text release.</p></div></section>
<details class="about"><summary>About This Translation</summary><p><strong>King James Version (Authorized Version)</strong>, first published in 1611. This reader presents the standardized 1769 text across the 66-book Protestant canon.</p>
<p>Presented by the <strong>Servants of the Way Digital Library</strong>. Italicized English words indicate translator-supplied words. Psalm superscriptions appear where present.</p>
<p>This Scripture reader does not include scanned pages, embedded Strong’s numbers, lexical conclusions, or commentary text. Original-language resources and historical commentaries remain in their independent libraries.</p></details>
</main><footer>King James Version · 1769 standardized text | Servants of the Way Digital Library | Scripture evidence and research tools maintained separately.</footer>
<script src="../../../assets/kjv1769/reader.js" defer></script></body></html>
'''

INDEX = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Servants of the Way | King James Version</title><style>body{font:18px/1.5 Georgia,serif;background:#f7f5ef;color:#192b32;max-width:1050px;margin:0 auto;padding:28px}h1{font-weight:normal}a{color:#1b555d}ul{columns:3;list-style:none;padding:0}li{break-inside:avoid;padding:4px 0}@media(max-width:640px){ul{columns:2}}</style></head><body><small>SERVANTS OF THE WAY · BIBLE FOUNDATION</small><h1>King James Version · 1769</h1><p>Presented by the Servants of the Way Digital Library. Select a book to read by chapter and verse. Original-language and historical commentary tools remain in their independent libraries.</p><ul>{items}</ul><p>King James Version, standardized 1769 text. Presented by the Servants of the Way Digital Library.</p></body></html>'''


def main():
    if BASE.exists(): shutil.rmtree(BASE)
    if OUT.exists():shutil.rmtree(OUT)
    BASE.mkdir(parents=True);OUT.mkdir(parents=True)
    zipbytes=SOURCE.read_bytes(); ziphash=h(zipbytes)
    manifest=[]
    with zipfile.ZipFile(SOURCE) as z:
        if z.testzip() is not None:raise ValueError('Bad source ZIP')
        all_names=z.namelist();usfm=[n for n in all_names if n.endswith('.usfm')]
        assert len(usfm)==66
        signature=z.read('signature.txt.asc').decode('utf8')
        signed={m[1]:m[0] for m in re.findall(r'^([a-f0-9]{64})  (.+)$',signature,re.M)}
        assert len(signed)==68 and set(signed)<=set(all_names)
        for n,hash_expect in signed.items():
            assert h(z.read(n))==hash_expect,(n,'signed checksum failed')
        map_data={re.match(r'\d+-([A-Z0-9]+)eng-kjv2006\.usfm',n).group(1):n for n in usfm}
        assert set(map_data)==set(x[0] for x in BOOKS)
        books_meta=[]; total_verses=0; total_chapters=0; note_count=0; superscription_count=0; strong_count=0; supplied_count=0
        for i,(code,name,slug) in enumerate(BOOKS):
            path=map_data[code]; sourcebytes=z.read(path);source=sourcebytes.decode('utf-8-sig')
            assert re.search(r'^\\id\s+'+re.escape(code)+r'\b',source,re.M)
            chaptermap, extras, notes,stats=chapter_from_source(source,code)
            chapters_count=len(chaptermap)
            assert sorted(chaptermap)==list(range(1,chapters_count+1))
            expected_chapters=sum(len(re.findall(r'^\\c\s+',source,re.M)) for _ in [0]);assert expected_chapters==chapters_count
            first=next(iter(chaptermap.values()))
            counts=[]; perbook_verse=0
            for ch,verses in chaptermap.items():
                numbers=[v['verse'] for v in verses]
                if numbers!=list(range(1,len(verses)+1)):raise ValueError(f'Uncontinuous verses {code}.{ch}: {numbers}')
                if not all(v['spans'] and all(x['text'] and x['kind'] in ('text','supplied') for x in v['spans']) for v in verses):raise ValueError('Invalid spans')
                # No Hebrew/Greek tags or Strong's IDs in chapter projection.
                joined=dumps(verses)
                assert not re.search(r'\\[a-zA-Z+]|\|strong=', joined), code
                rel=f'data/kjv1769/{slug}/chapters/{ch:02d}.json'
                obj={'schema_version':'1.0.0','edition_id':EDITION,'book_code':code,'chapter':ch,'verses':verses}
                jwrite(rel,obj)
                counts.append({'chapter':ch,'verse_count':len(verses),'sha256':h((BASE/rel).read_bytes())})
                perbook_verse+=len(verses)
            total_chapters+=chapters_count;total_verses+=perbook_verse
            strong_count+=stats['source_word_tags_removed'];note_count+=stats['source_footnote_markers_removed'];supplied_count+=stats['supplied_spans']
            sp_count=sum(len(e['superscriptions']) for e in extras.values());superscription_count+=sp_count
            predecessor=BOOKS[i-1][0] if i else None
            successor=BOOKS[i+1][0] if i<65 else None
            catalog={'schema_version':'1.0.0','edition_id':EDITION,'book_code':code,'book_name':name,'book_order':i+1,
                     'canonical_ids':f'{code}.{{chapter}}.{{verse}}','edition_ids':f'{EDITION}:{code}.{{chapter}}.{{verse}}',
                     'chapter_count':chapters_count,'verse_count':perbook_verse,
                     'traditional_verse_positions':perbook_verse,'omitted_from_main_text':[],
                     'chapter_path_template':f'{slug}/chapters/{{chapter:02d}}.json',
                     'predecessor_book_code':predecessor,'successor_book_code':successor,
                     'source_provenance':f'books/{slug}/SOURCE_INVENTORY.json','reader':f'books/{slug}/site/index.html',
                     'note':'Text-only KJV1769 projection of the pinned eBible eng-kjv2006 source. No scanned pages, embedded Strong’s, or lexical claims.'}
            jwrite(f'data/kjv1769/catalog-{slug}.json',catalog)
            jwrite(f'data/kjv1769/{slug}/chapter-extras.json',{'edition_id':EDITION,'book_code':code,'chapters':{str(c):e for c,e in extras.items() if e['superscriptions'] or e['source_section_headings']},'note':'Non-verse Psalm superscriptions and edition section headings preserved separately from numbered Bible text.'})
            jwrite(f'data/kjv1769/{slug}/source-footnotes.json',{'edition_id':EDITION,'book_code':code,'chapters':{str(c):ns for c,ns in notes.items()},'note':'Original USFM translator notes keyed to verses; excluded from running Scripture and not presented as independent historical commentary.'})
            jwrite(f'data/kjv1769/{slug}/chapter-checks.json',{'edition_id':EDITION,'book_code':code,'chapter_count':chapters_count,'verse_count':perbook_verse,'chapters':counts})
            jwrite(f'books/{slug}/SOURCE_INVENTORY.json',{'edition_id':EDITION,'book_code':code,
                    'original_archive':'eng-kjv2006_usfm.zip','archive_sha256':ziphash,'usfm_filename':path,'usfm_sha256':h(sourcebytes),
                    'acquisition':'owner-uploaded vetted archive, 2026-11-09','original_source_page':SOURCE_URL,
                    'source_edition':'King James Version, standardized text of 1769; eBible eng-kjv2006 USFM source',
                    'source_archive_preserved_outside_public_repository':True,
                    'source_usfm_contains_strongs_annotations':True,'published_chapter_json_contains_strongs':False,
                    'historical_scans_included':False,'uk_printing_rights_notice':'UK Crown rights noted by source; no claim that UK printing rights are waived.'})
            jwrite(f'books/{slug}/VALIDATION_REPORT.json',{'status':'PASS_SOURCE_PROJECTION_CHECKS','source_archive_sha256':ziphash,
                   'edition_id':EDITION,'book_code':code,'book_name':name,'chapter_count':chapters_count,'verse_count':perbook_verse,
                   'source_verse_markers':len(re.findall(r'^\\v\s+',source,re.M)),
                   'word_markup_removed':stats['source_word_tags_removed'],
                   'footnote_markup_removed':stats['source_footnote_markers_removed'],
                   'source_supplied_word_runs':len(re.findall(r'\\\+?add(?=\s)',source)),
                   'superscriptions_preserved':sp_count,
                   'data_schema':'ASV-style v1.0.0 KJV identity variant',
                   'limitations':'No independently digitized print-edition collation or browser deployment verification is claimed.'})
            write(f'books/{slug}/site/index.html',PAGE.format(code=code,slug=slug,name=name))
            write(f'books/{slug}/index.html',f'<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=site/index.html#{code}.1.1"><title>KJV {name}</title><a href="site/index.html#{code}.1.1">Read {name}</a></html>\n')
            write(f'books/{slug}/README.md',f'# {name} | King James Version (1769 standardized text)\n\nServants of the Way Digital Library | Book {i+1} of 66.\n\n{chapters_count} chapters, {perbook_verse:,} verses. Verse identity `{code}.1.1`; edition identity `{EDITION}:{code}.1.1`.\n\nSource: owner-vetted eBible `eng-kjv2006` USFM ZIP; exact SHA-256 locks in `SOURCE_INVENTORY.json`. The running chapter JSON excludes Strong’s tags and original translator footnotes, which are archived in separate provenance-bearing metadata. No historical page scans are included.\n\n`books/{slug}/site/index.html` provides an isolated Scripture-text reader. Word-study/commentary interfaces are deferred to independently governed libraries.\n')
            books_meta.append({'code':code,'name':name,'slug':slug,'order':i+1,'chapter_count':chapters_count,'verse_count':perbook_verse,
                              'verse_id_pattern':f'{code}.{{chapter}}.{{verse}}','edition_verse_id_pattern':f'{EDITION}:{code}.{{chapter}}.{{verse}}'})
            manifest.append({'book_code':code,'source_file':path,'sha256':h(sourcebytes),'chapter_count':chapters_count,'verse_count':perbook_verse})
        assert total_chapters==1189,(total_chapters,'chapters')
        assert total_verses==31102,(total_verses,'verses')
        # A publisher-specific source archive can contain the word-tagged input, but publication contains only text projections.
        jwrite('data/kjv1769/books.json',{'schema_version':'1.0.0','edition_id':EDITION,'title':'King James Version (1769 standardized text)','book_count':66,'chapter_count':total_chapters,'verse_count':total_verses,'books':books_meta})
        jwrite('data/kjv1769/route-map.json',{'schema_version':'1.0.0','edition_id':EDITION,
               'canonical_id_pattern':'{BOOK}.{CHAPTER}.{VERSE}','edition_verse_id_pattern':'KJV1769:{BOOK}.{CHAPTER}.{VERSE}',
               'book_catalog_path':'data/kjv1769/catalog-{slug}.json',
               'chapter_text_path':'data/kjv1769/{slug}/chapters/{chapter:02d}.json',
               'separate_original_language_resource':'SOTW-Original-Languages original-language-resources and SOTW-Original-Languages-2 original-language-resources',
               'language_resource_route_map':'study-data/v1/route-map.json',
               'study_evidence_key_example':'verses["GEN.1.1"].KJV1769',
               'note':'KJV1769 study word-link evidence is separate from English text; tagged native USFM word ordinals are NOT direct English reading-display token offsets.',
               'historical_commentary_resource':'SOTW-Historical-Commentaries/historical-commentary-resources',
               'commentary_join_id':'GEN.1.1',
               'published_integration_status':'NOT_BUILT; this is a logical linking contract only',
               'facsimile_pages_available':False})
        jwrite('docs/SOURCE_LOCK.json',{'source_archive':'eng-kjv2006_usfm.zip','archive_sha256':ziphash,
               'source_page':SOURCE_URL,'upstream_download':SOURCE_ZIP_URL,
               'source_title':'King James (Authorized) Version',
               'source_description':'standardized text of 1769, protocanon only, Strong’s tags present in original USFM but excluded from published text projection',
               'source_signed_manifest':'signature.txt.asc','signed_sha256_entry_count':len(signed),
               'signed_manifest_hash_verification':'68_OF_68_MATCH',
               'signed_manifest_signature_cryptographically_verified':False,
               'source_files':manifest,
               'rights':'Source identifies public domain outside UK; Crown-related UK printing constraints noted; no scanning reproduction.'})
        jwrite('docs/EDITION.json',{'schema_version':'1.0.0','edition_id':EDITION,'translation_title':'King James Version','also_known_as':'Authorized Version',
               'first_publication_year':1611,'standardization_year':1769,'digital_source_id':'eng-kjv2006',
               'digital_format':'USFM','canon':'Protestant 66 books','source_url':SOURCE_URL,'source_archive_sha256':ziphash,
               'presenting_library':'Servants of the Way Digital Library',
               'about':'King James Version (standardized 1769 text), presented by the Servants of the Way Digital Library.',
               'rights_summary':'Public-domain text outside the UK; UK Crown rights affecting printing remain according to the source.',
               'capabilities':{'verses':True,'chapter_navigation':True,'book_navigation':True,'supplied_word_italics':True,
                 'superscriptions':True,'digital_source_note_archival':True,'source_pdf_scan':False,'embedded_strongs':False,
                 'original_language_word_click_ui':False,'historical_commentary_ui':False}})
        write('docs/RIGHTS_AND_PROVENANCE.md',f'''# KJV1769 source, rights, and presentation\n\n**Edition:** King James (Authorized) Version, standardized 1769 text, digital source `eng-kjv2006`, 66-book protocanon.\n\n**Source:** [Original eBible edition record]({SOURCE_URL}). The exact owner-supplied USFM archive (`eng-kjv2006_usfm.zip`) has SHA-256 `{ziphash}`. Its embedded signed SHA-256 manifest lists 68 files, all independently checksum-matched. The OpenPGP signature itself has **not** been verified against an independently trusted key. See `docs/SOURCE_LOCK.json` for every source-file checksum.\n\n**Copyright:** The included source notice identifies this as public-domain Scripture text outside the United Kingdom, while noting surviving UK Crown printing rights. No broader territorial rights representation is made here. The editorial arrangement and code of this release are not claims of ownership of the historical Bible translation.\n\n**Public credit:** “Presented by the Servants of the Way Digital Library.” Reader links go directly to the source edition record. There is no advertising or third-party hosting endorsement. Source/origin provenance is retained in internal technical documentation.\n\n**Source exclusions:** Source USFM includes Strong’s word markup, source translator footnotes, Psalm superscriptions, and supplied-word typography. Strong’s tags are removed from verse text, because original-language evidence is maintained in a separate library. Footnotes are stored separately, superscriptions are preserved separately and shown above their chapter where applicable, and supplied-word italics appear as `spans[].kind=\"supplied\"`. Original USFM source archive is not republished in this text-only distribution. No historical scanned pages are included.\n''')
        write('docs/COMPATIBILITY.md','''# Stable references and existing SOTW foundations\n\nThe unqualified reference `GEN.1.1` is a shared Scripture identity, **not** a text or alignment claim. KJV text is stored as `KJV1769:GEN.1.1` and uses the ASV-style verse record keys `id`, `edition_verse_id`, `verse`, `spans`, and `paragraph_start`. All 66 ASV book slugs and canonical book codes were reused without altering ASV.\n\nThe original-language sites already contain chapter-level `verses["GEN.1.1"].KJV1769` word-link evidence. The native tagged-USFM word ordinals are **not** English display token offsets. Verse-click expansion must use those separate approved datasets and their versioned contracts later; this release contains no lexical or Strong’s payload and makes no fabricated token-position claims.\n\nThe historical-commentary library has separately anchored commentary keyed by shared Scripture IDs; its own versioning, rights, and coverage govern any future connection. No commentary is copied, nor is an API/reader implementation claimed.\n\nThis is an independent translation data release. It does not modify the existing ASV, original-language, historical-commentary, or CGBC player repositories.\n''')
        write('docs/UPLOAD_GUIDE.md','''# Owner manual installation\n\n1. Establish or select the independent KJV translation repository under the intended Servants of the Way GitHub organization. The ZIPs are **repository-root-relative** and do not contain an enclosing wrapper folder. No target repository is assumed to exist yet.\n2. Extract each `UPLOAD_PART_*.zip` locally. Upload/merge its contents at the **repository root**, preserving nested `data/`, `books/`, `docs/`, and `assets/` paths. The parts are disjoint; no previous files must be overwritten. Do not upload a `.zip` file as an inert file expecting GitHub to extract it. The uploader's per-batch file limit is respected.\n3. Place the site on GitHub Pages (branch `main`, root) only if you choose. This package itself does not deploy a website. Open `books/genesis/site/index.html` and test chapter selection, verse selection, `#GEN.1.1`, `?ref=GEN.1.1`, and next/previous navigation. Repeat on a Psalm, a Gospel, and Revelation.\n4. Verify 66 catalogs and reader paths, 1,189 chapter files, 31,102 verse records, supplied italics, Psalm headings, source notes, 68 signed-manifest SHA checks, and source/release hashes.\n5. Confirm no KJV facsimile PDFs, embedded Strong’s fields, original-language data, or commentary data were added. Study tools and CGBC player integration remain separate projects.\n\nThe source archive with embedded Strong’s tags is not copied into the public KJV repo. Keep the original owner-uploaded source ZIP and its SHA-256 lock outside this release. For an independent rebuild, run the separately supplied `scripts/build_kjv1769.py` using the exact archive, after adjusting its input/output paths for the local environment.\n''')
        write('docs/QA_REPORT.md',f'''# KJV1769 publication-data audit | {TODAY}\n\n- **Source ZIP SHA-256:** `{ziphash}`\n- **Source entries:** 70 total: 66 USFM books, `copr.htm`, `latin.css`, `keys.asc`, and `signature.txt.asc`.\n- **Signed SHA-256 entries:** {len(signed)} of {len(signed)} matched, including all 66 books. No assertion of cryptographically verified OpenPGP signature.\n- **Canonical scope:** 66 books, {total_chapters:,} chapters, {total_verses:,} verse records; contiguous chapter/verse numbering in the source.\n- **Original source word tags removed:** {strong_count:,}; this is NOT a count of verified original-language alignments.\n- **Source translator footnotes separated:** {note_count:,}; publication verse texts exclude their content; separately keyed note metadata preserved.\n- **Source paragraph markers / editorial cues:** paragraph-start flags retained, Psalm superscriptions {superscription_count} preserved in separate chapter extras.\n- **Source-supplied runs:** {supplied_count:,} projected as italicized spans (the detailed per-book marker counts are authoritative where needed).\n- **Schema:** ASV-compatible chapter shape with `edition_id=KJV1769` and shared Scripture IDs.\n- **Provenance:** source archive hash and per-book source file hashes.\n- **No claim:** exhaustive comparison with a historical 1769 print, independent textual source collation, verified word alignments, deployed GitHub Pages, or complete manual browser QA.\n- **Status:** PASS for source-anchored structural projection and hash checks; browser deployment/integration remains pending owner installation.\n''')
        write('README.md',f'''# Servants of the Way Digital Library | King James Version (1769)\n\nA standalone, text-only Scripture translation foundation built from the owner-vetted public-domain eBible **`eng-kjv2006`** USFM archive. This source represents the King James Version's standardized **1769** text, not a facsimile of the first **1611** printing.\n\n**Coverage:** 66 books · 1,189 chapters · 31,102 verses. All chapter data use shared reference IDs such as `GEN.1.1` and edition IDs such as `KJV1769:GEN.1.1`, retaining ASV book slugs and catalog structure.\n\n- `index.html`: book selection.\n- `books/<slug>/site/index.html`: individual book/chapter/verse reader.\n- `data/kjv1769/<slug>/chapters/NN.json`: Scripture text with italicized supplied spans.\n- `data/kjv1769/catalog-<slug>.json`: per-book metadata.\n- `data/kjv1769/route-map.json`: logical future links to external original-language and commentary resources.\n- `docs/EDITION.json`: source/rights/credit metadata shared across all books.\n- `docs/SOURCE_LOCK.json`: archive and per-file SHA-256 verification.\n- `docs/QA_REPORT.md`: exact checks, limitations.\n- `docs/UPLOAD_GUIDE.md`: manual GitHub-root installation.\n\n**Presented by the Servants of the Way Digital Library.** Source edition record: {SOURCE_URL}. Public-domain Scripture text outside the United Kingdom, subject to UK Crown printing-rights restrictions described by the source.\n\nNo scanned page PDFs, Strong’s numbers, original-language conclusions, or historical-commentary text are published as part of the KJV chapter records. These other resources remain separately governed and will be connected by a future UI. This release does not change the ASV repository or CGBC player.\n''')
        write('assets/kjv1769/reader.css',CSS)
        write('assets/kjv1769/reader.js',JS)
        write('index.html',INDEX.replace('{items}',''.join(f'<li><a href="books/{slug}/site/index.html#{code}.1.1">{name}</a></li>' for code,name,slug in BOOKS)))
        # Include the reproducible build tool itself, but it expects a local source ZIP; not a source-tag publication.
        build_source=Path(__file__).read_text()
        write('scripts/build_kjv1769.py',build_source)
        # Read all file bytes from disk once and commit exact release byte hashes.
        filelist=[str(p.relative_to(BASE)).replace('\\','/') for p in BASE.rglob('*') if p.is_file()]
        filelist.sort()
        content_sha={p:h((BASE/p).read_bytes()) for p in filelist}
        jwrite('RELEASE_MANIFEST.json',{'schema_version':'1.0.0','edition_id':EDITION,'release_date':TODAY,
               'source_archive_sha256':ziphash,'files':content_sha,'file_count_excluding_manifest':len(filelist),
               'sources_published_with_embedded_strongs':False,'release_type':'owner-manual-upload; not deployed'})
        final_files=sorted(str(p.relative_to(BASE)).replace('\\','/') for p in BASE.rglob('*') if p.is_file())
        # enforce publication data are not carrying source Strong's even accidentally.
        chapter_files=[f for f in final_files if re.match(r'data/kjv1769/.+/chapters/\d\d+\.json$',f)]
        assert len(chapter_files)==1189
        assert len([x for x in final_files if x.endswith('/site/index.html')])==66
        for f in chapter_files:
            b=(BASE/f).read_bytes()
            assert b'"strong"' not in b.lower() and b'\\w ' not in b
        # Source zip archive also omitted.
        assert not any(f.endswith('.usfm') or f.endswith('.pdf') for f in final_files)
        # part archive: <=95 repository root file paths per upload. Parts disjoint and together exhaustive.
        chunks=[final_files[i:i+95] for i in range(0,len(final_files),95)]
        part_files=[]
        for i,paths in enumerate(chunks,1):
            filename=f'UPLOAD_PART_{i:02d}_of_{len(chunks):02d}.zip'
            p=OUT/filename
            with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zp:
                for path in paths:zp.write(BASE/path,arcname=path)
            with zipfile.ZipFile(p) as check:
                assert check.testzip() is None and len(check.namelist())<=99
            part_files.append({'name':filename,'file_count':len(paths),'bytes':p.stat().st_size,'sha256':h(p.read_bytes()),'paths':paths})
        jplan={'release_date':TODAY,'repository_root_file_count':len(final_files),'zip_parts':len(part_files),
               'upload_part_max_files':max(len(p['paths']) for p in part_files),
               'source_archive_sha256':ziphash,'part_manifest':part_files}
        (OUT/'UPLOAD_PLAN.json').write_text(dumps(jplan),encoding='utf-8')
        # Complete copy for local inspection; not uploadable as a single browser batch.
        full=OUT/'SOTW_KJV1769_COMPLETE_REPOSITORY_ROOT.zip'
        with zipfile.ZipFile(full,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zp:
            for p in final_files:zp.write(BASE/p,arcname=p)
        # one convenience download: all upload parts + outside release manifests, with instructions.
        delivery=Path('/mnt/data/SOTW_KJV1769_MANUAL_UPLOAD_KIT_2026-11-09.zip')
        with zipfile.ZipFile(delivery,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zp:
            zp.write(OUT/'UPLOAD_PLAN.json','UPLOAD_PLAN.json')
            zp.write(BASE/'docs/UPLOAD_GUIDE.md','UPLOAD_GUIDE.md')
            for p in sorted(OUT.glob('UPLOAD_PART_*.zip')):zp.write(p,arcname=p.name)
        # Basic integrity of the 18ish part deliveries.
        assert zipfile.ZipFile(delivery).testzip() is None
        summary={'status':'BUILT_DATA_NOT_DEPLOYED','source_archive_sha256':ziphash,'chapters':total_chapters,'verses':total_verses,
                 'books':66,'strong_source_annotations_removed':strong_count,'notes_removed_from_verse_text':note_count,
                 'psalm_superscriptions':superscription_count,'release_file_count':len(final_files),'upload_part_count':len(part_files),
                 'max_files_per_part':max(len(p['paths']) for p in part_files),'complete_bytes':full.stat().st_size,
                 'kit_bytes':delivery.stat().st_size,'kit_sha256':h(delivery.read_bytes()),'delivery':str(delivery)}
        (OUT/'SUMMARY.json').write_text(dumps(summary),encoding='utf8')
        print(dumps(summary))

if __name__=='__main__':main()

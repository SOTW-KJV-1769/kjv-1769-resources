(()=>{
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

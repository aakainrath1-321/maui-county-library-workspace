function renderAtlasMarkdown(text){
 const safe=esc(text);
 let s=safe.replace(/`([^`\n]+)`/g,'<code>$1</code>')
 .replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>')
 .replace(/__([^_\n]+)__/g,'<strong>$1</strong>')
 .replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,!?:;])/g,'$1<em>$2</em>')
 .replace(/(^|[\s(])_([^_\n]+)_(?=$|[\s).,!?:;])/g,'$1<em>$2</em>');
 const lines=s.split(/\r?\n/);let html='',list='';
 const close=()=>{if(list){html+=`</${list}>`;list=''}};
 for(const raw of lines){const line=raw.trim();let m=line.match(/^[-•]\s+(.+)/);
  if(m){if(list!=='ul'){close();html+='<ul>';list='ul'}html+=`<li>${m[1]}</li>`;continue}
  m=line.match(/^\d+[.)]\s+(.+)/);
  if(m){if(list!=='ol'){close();html+='<ol>';list='ol'}html+=`<li>${m[1]}</li>`;continue}
  close();if(line)html+=`<p>${line}</p>`;
 }close();return html||'<p></p>';
}
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)],body=document.body,scrim=$('#scrim'),toast=$('#toast');function showToast(m){toast.textContent=m;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),2200)}function openDrawer(el){el.classList.add('open');scrim.classList.add('open')}function closeDrawers(){$$('.drawer').forEach(d=>d.classList.remove('open'));scrim.classList.remove('open')}$$('[data-atlas-open]').forEach(b=>b.addEventListener('click',()=>openDrawer($('#atlasDrawer'))));$$('[data-feedback-open]').forEach(b=>b.addEventListener('click',()=>openDrawer($('#feedbackDrawer'))));$$('[data-close]').forEach(b=>b.addEventListener('click',closeDrawers));scrim.addEventListener('click',closeDrawers);
let editMode=localStorage.getItem('mclw-edit-mode')==='1';function applyEdit(){body.classList.toggle('edit-mode',editMode);$$('[data-edit-toggle]').forEach(b=>b.textContent=editMode?'✓ Done Editing':'✎ Edit Workspace')}applyEdit();$$('[data-edit-toggle]').forEach(b=>b.addEventListener('click',()=>{editMode=!editMode;localStorage.setItem('mclw-edit-mode',editMode?'1':'0');applyEdit();showToast(editMode?'Prototype Edit Mode enabled':'Edit Mode closed')}));$$('[data-demo-add]').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();const kind=b.dataset.demoAdd||'resource',name=prompt(`Demo ${kind} name:`);if(name){localStorage.setItem(`mclw-demo-${Date.now()}`,JSON.stringify({kind,name,path:location.pathname}));showToast(`${name} added to your local demo`)}}));
const search=$('#workspaceSearch'),results=$('#searchResults');let timer;search?.addEventListener('input',()=>{clearTimeout(timer);const q=search.value.trim();if(!q){results.classList.remove('open');return}timer=setTimeout(async()=>{const data=await fetch(`/api/search?q=${encodeURIComponent(q)}`).then(r=>r.json());results.innerHTML=data.map(x=>`<a href="${x.url}">${x.label}</a>`).join('')||'<a>No exact result — ask Atlas</a>';results.classList.add('open')},150)});
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}const atlasForm=$('#atlasForm'),atlasInput=$('#atlasInput'),thread=$('#atlasThread');
const atlasHistoryKey='mclw-atlas-history-v1';
let atlasHistory=[];
try{atlasHistory=JSON.parse(sessionStorage.getItem(atlasHistoryKey)||'[]')}catch{atlasHistory=[]}
function saveAtlasHistory(){sessionStorage.setItem(atlasHistoryKey,JSON.stringify(atlasHistory.slice(-16)))}
function atlasActionElement(a){
  if(a.type==='navigate'&&a.url){const el=document.createElement('a');el.href=a.url;el.textContent=a.label||'Open';return el}
  const el=document.createElement('button');el.type='button';el.textContent=a.label||'Run action';
  el.onclick=()=>{
    if(a.type==='open_feedback'){closeDrawers();setTimeout(()=>openDrawer($('#feedbackDrawer')),120)}
    if(a.type==='enter_edit_mode'){editMode=true;localStorage.setItem('mclw-edit-mode','1');applyEdit();showToast('Atlas enabled Edit Mode')}
  };
  return el
}
async function askAtlas(q){
  if(!q)return;
  thread.insertAdjacentHTML('beforeend',`<div class="message user">${esc(q)}</div>`);
  atlasHistory.push({role:'user',text:q});saveAtlasHistory();atlasInput.value='';
  const loader=document.createElement('div');loader.className='message atlas';loader.textContent='Thinking…';thread.appendChild(loader);thread.scrollTop=thread.scrollHeight;
  try{
    const res=await fetch('/api/atlas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:q,history:atlasHistory.slice(0,-1),context:location.pathname})});
    const data=await res.json();loader.remove();
    if(!res.ok||!data.ok)throw new Error(data.error||'Atlas is unavailable.');
    thread.insertAdjacentHTML('beforeend',`<div class="message atlas">${renderAtlasMarkdown(data.reply)}</div>`);
    atlasHistory.push({role:'model',text:data.reply});saveAtlasHistory();
    if(data.actions?.length){
      const wrap=document.createElement('div');wrap.className='atlas-actions';
      data.actions.forEach(a=>wrap.appendChild(atlasActionElement(a)));
      thread.appendChild(wrap)
    }
  }catch(e){
    loader.remove();
    thread.insertAdjacentHTML('beforeend',`<div class="message atlas">Atlas couldn’t connect: ${esc(e.message)}</div>`)
  }
  thread.scrollTop=thread.scrollHeight
}
atlasForm?.addEventListener('submit',e=>{e.preventDefault();askAtlas(atlasInput.value.trim())});
$$('[data-atlas-prompt]').forEach(b=>b.addEventListener('click',()=>askAtlas(b.dataset.atlasPrompt)));
$$('input[name="identity"]').forEach(r=>r.addEventListener('change',()=>$('#feedbackNameWrap').classList.toggle('hidden',$('input[name="identity"]:checked').value!=='named')));$('#feedbackForm')?.addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.currentTarget),p=Object.fromEntries(fd.entries());p.anonymous=p.identity!=='named';const res=await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)}),data=await res.json();$('#feedbackStatus').textContent=data.message||data.error;if(res.ok){showToast('Feedback saved. Thank you.');e.currentTarget.reset();$('#feedbackNameWrap').classList.add('hidden')}});
const boardKey='mclw-demo-board';function renderPosts(){const feed=$('#boardFeed');if(!feed)return;let posts=[];try{posts=JSON.parse(localStorage.getItem(boardKey)||'[]')}catch{}posts.forEach(p=>feed.insertAdjacentHTML('beforeend',`<article class="board-post"><div class="post-meta"><strong>${esc(p.name||'Demo staff member')}</strong><span>Local demo · This device</span></div><p>${esc(p.body)}</p></article>`))}renderPosts();$('#boardPostButton')?.addEventListener('click',()=>{const name=$('#boardName').value.trim(),msg=$('#boardMessage').value.trim();if(!msg)return showToast('Write a short post first.');let posts=[];try{posts=JSON.parse(localStorage.getItem(boardKey)||'[]')}catch{}posts.push({name:name||'Demo staff member',body:msg});localStorage.setItem(boardKey,JSON.stringify(posts));location.reload()});

(function(){const b=document.getElementById('securityStatusBtn'),d=document.getElementById('securityDrawer'),c=document.getElementById('closeSecurity');if(!b||!d)return;function open(){document.querySelectorAll('.drawer').forEach(x=>{if(x!==d){x.classList.remove('open');x.setAttribute('aria-hidden','true')}});d.classList.add('open');d.setAttribute('aria-hidden','false')}function close(){d.classList.remove('open');d.setAttribute('aria-hidden','true')}b.addEventListener('click',open);if(c)c.addEventListener('click',close);document.addEventListener('keydown',e=>{if(e.key==='Escape')close()})})();


/* V8 prototype editing system */
(function(){
 const toolbar=document.getElementById('editToolbar');
 const modal=document.getElementById('editorModal');
 const form=document.getElementById('editorForm');
 const close=document.getElementById('editorClose');
 const cancel=document.getElementById('editorCancel');
 const kindInput=document.getElementById('editorKind');
 const titleInput=document.getElementById('editorItemTitle');
 const urlInput=document.getElementById('editorUrl');
 const descInput=document.getElementById('editorDescription');
 const fileInput=document.getElementById('editorFile');
 const urlWrap=document.getElementById('editorUrlWrap');
 const fileWrap=document.getElementById('editorFileWrap');
 const modalTitle=document.getElementById('editorTitle');
 const storeKey='mclw-v8-local-edits';

 function load(){try{return JSON.parse(localStorage.getItem(storeKey)||'[]')}catch{return[]}}
 function save(items){localStorage.setItem(storeKey,JSON.stringify(items))}
 function openEditor(kind){
   if(!modal)return;
   kindInput.value=kind;form.reset();kindInput.value=kind;
   modalTitle.textContent='Add '+kind.charAt(0).toUpperCase()+kind.slice(1);
   urlWrap.style.display=kind==='link'?'grid':'none';
   fileWrap.style.display=kind==='file'?'grid':'none';
   modal.classList.add('open');modal.setAttribute('aria-hidden','false');titleInput.focus();
 }
 function closeEditor(){if(!modal)return;modal.classList.remove('open');modal.setAttribute('aria-hidden','true')}
 function render(){
   document.querySelectorAll('.local-edit-item').forEach(x=>x.remove());
   for(const item of load()){
     let zone=document.querySelector(`[data-zone="${item.zone||'updates'}"]`)||document.querySelector('[data-zone="updates"]');
     if(!zone)continue;
     const el=document.createElement(item.kind==='link'?'a':'article');
     el.className='local-edit-item';
     if(item.kind==='link'&&item.url){el.href=item.url;el.target='_blank';el.rel='noopener'}
     el.innerHTML=`<strong>${esc(item.title)}</strong>${item.description?`<small>${esc(item.description)}</small>`:''}${item.fileName?`<small>File: ${esc(item.fileName)}</small>`:''}<button type="button" class="local-edit-remove" data-remove-edit="${item.id}">Remove</button>`;
     zone.appendChild(el);
   }
   document.querySelectorAll('[data-remove-edit]').forEach(b=>b.addEventListener('click',e=>{
     e.preventDefault();e.stopPropagation();
     save(load().filter(x=>x.id!==b.dataset.removeEdit));render();showToast('Demo item removed');
   }));
 }
 document.querySelectorAll('[data-editor-add]').forEach(b=>b.addEventListener('click',()=>openEditor(b.dataset.editorAdd)));
 close?.addEventListener('click',closeEditor);cancel?.addEventListener('click',closeEditor);
 modal?.addEventListener('click',e=>{if(e.target===modal)closeEditor()});
 form?.addEventListener('submit',e=>{
   e.preventDefault();
   const kind=kindInput.value;
   const item={
     id:String(Date.now()),kind,
     title:titleInput.value.trim(),
     url:urlInput.value.trim(),
     description:descInput.value.trim(),
     fileName:fileInput.files?.[0]?.name||'',
     zone:kind==='link'?'quick-links':kind==='update'?'updates':kind==='section'?'updates':kind==='folder'?'updates':kind==='file'?'updates':'updates'
   };
   if(!item.title)return;
   const items=load();items.push(item);save(items);render();closeEditor();showToast(`${item.title} added to your local demo`);
 });
 document.querySelector('[data-editor-reset]')?.addEventListener('click',()=>{
   if(confirm('Remove all prototype edits saved in this browser?')){localStorage.removeItem(storeKey);render();showToast('Local demo edits reset')}
 });
 document.querySelectorAll('[data-edit-card]').forEach(b=>b.addEventListener('click',e=>{
   e.preventDefault();e.stopPropagation();
   const card=b.closest('[data-editable-card]');
   if(b.dataset.editCard==='title'){
     const current=card.querySelector('h3').textContent;
     const value=prompt('Demo branch label:',current);
     if(value){card.querySelector('h3').textContent=value;showToast('Demo label updated for this session')}
   }else{
     showToast('Prototype image replacement is represented here; production would open a secured upload workflow.');
   }
 }));
 render();
})();

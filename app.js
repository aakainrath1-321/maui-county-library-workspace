
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const body=document.body, scrim=$('#scrim'), toast=$('#toast');

function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function showToast(msg){if(!toast)return;toast.textContent=msg;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),2200)}
function openDrawer(el){if(!el)return;$$('.drawer').forEach(d=>{if(d!==el){d.classList.remove('open');d.setAttribute('aria-hidden','true')}});el.classList.add('open');el.setAttribute('aria-hidden','false');scrim?.classList.add('open')}
function closeDrawers(){$$('.drawer').forEach(d=>{d.classList.remove('open');d.setAttribute('aria-hidden','true')});scrim?.classList.remove('open')}

$$('[data-atlas-open]').forEach(b=>b.addEventListener('click',()=>openDrawer($('#atlasDrawer'))));
$$('[data-feedback-open]').forEach(b=>b.addEventListener('click',()=>openDrawer($('#feedbackDrawer'))));
$$('[data-close]').forEach(b=>b.addEventListener('click',closeDrawers));
$('#securityStatusBtn')?.addEventListener('click',()=>openDrawer($('#securityDrawer')));
$('#securityTopLink')?.addEventListener('click',()=>openDrawer($('#securityDrawer')));
$('#closeSecurity')?.addEventListener('click',closeDrawers);
scrim?.addEventListener('click',closeDrawers);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeDrawers();$('#editorModal')?.classList.remove('open')}});

/* Edit mode */
let editMode=localStorage.getItem('mclw-edit-mode')==='1';
function applyEdit(){
  body.classList.toggle('edit-mode',editMode);
  $$('[data-edit-toggle]').forEach(b=>{b.textContent=editMode?'✓ Done Editing':'✎ Edit Workspace'});
  $('#globalEditBanner')?.setAttribute('aria-hidden',editMode?'false':'true');
}
applyEdit();
$$('[data-edit-toggle]').forEach(b=>b.addEventListener('click',()=>{editMode=!editMode;localStorage.setItem('mclw-edit-mode',editMode?'1':'0');applyEdit();showToast(editMode?'Edit Mode enabled — look for editable controls':'Edit Mode closed')}));

/* Search */
const search=$('#workspaceSearch'),results=$('#searchResults'),branchFilter=$('#branchFilter');let searchTimer;
async function runSearch(){
  if(!search||!results)return;
  const q=search.value.trim();const branch=branchFilter?.value||'';
  if(!q&&!branch){results.classList.remove('open');return}
  let query=q||branch;
  try{
    const data=await fetch(`/api/search?q=${encodeURIComponent(query)}`).then(r=>r.json());
    const filtered=branch?data.filter(x=>x.url.includes(`/branch/${branch}`)):data;
    results.innerHTML=(filtered.length?filtered:data).slice(0,10).map(x=>`<a href="${x.url}">${esc(x.label)}</a>`).join('')||'<a href="#" data-atlas-open>No exact result — ask Atlas</a>';
    results.classList.add('open');
  }catch{results.classList.remove('open')}
}
search?.addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(runSearch,150)});
branchFilter?.addEventListener('change',runSearch);
document.addEventListener('click',e=>{if(results&&!e.target.closest('.hero-search'))results.classList.remove('open')});

/* Safe, limited Markdown rendering for Atlas */
function renderAtlasMarkdown(text){
  let s=esc(text);
  s=s.replace(/`([^`\n]+)`/g,'<code>$1</code>')
     .replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>')
     .replace(/__([^_\n]+)__/g,'<strong>$1</strong>')
     .replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,!?:;])/g,'$1<em>$2</em>')
     .replace(/(^|[\s(])_([^_\n]+)_(?=$|[\s).,!?:;])/g,'$1<em>$2</em>');
  const lines=s.split(/\r?\n/);let html='',list='';
  const close=()=>{if(list){html+=`</${list}>`;list=''}};
  for(const raw of lines){
    const line=raw.trim();let m=line.match(/^[-•]\s+(.+)/);
    if(m){if(list!=='ul'){close();html+='<ul>';list='ul'}html+=`<li>${m[1]}</li>`;continue}
    m=line.match(/^\d+[.)]\s+(.+)/);
    if(m){if(list!=='ol'){close();html+='<ol>';list='ol'}html+=`<li>${m[1]}</li>`;continue}
    close();if(line)html+=`<p>${line}</p>`;
  }
  close();return html||'<p></p>';
}

/* Atlas */
const atlasForm=$('#atlasForm'),atlasInput=$('#atlasInput'),thread=$('#atlasThread');
const atlasHistoryKey='mclw-atlas-history-v9';let atlasHistory=[];
try{atlasHistory=JSON.parse(sessionStorage.getItem(atlasHistoryKey)||'[]')}catch{atlasHistory=[]}
function saveAtlasHistory(){sessionStorage.setItem(atlasHistoryKey,JSON.stringify(atlasHistory.slice(-16)))}
function handleAtlasAction(a){
  if(a.type==='open_feedback'){closeDrawers();setTimeout(()=>openDrawer($('#feedbackDrawer')),120)}
  if(a.type==='enter_edit_mode'){editMode=true;localStorage.setItem('mclw-edit-mode','1');applyEdit();showToast('Atlas enabled Edit Mode')}
}
function atlasActionElement(a){
  if(a.type==='navigate'&&a.url){const el=document.createElement('a');el.href=a.url;el.textContent=a.label||'Open';return el}
  const el=document.createElement('button');el.type='button';el.textContent=a.label||'Run action';el.addEventListener('click',()=>handleAtlasAction(a));return el
}
async function askAtlas(q){
  if(!q||!thread)return;
  thread.insertAdjacentHTML('beforeend',`<div class="message user">${esc(q)}</div>`);
  atlasHistory.push({role:'user',text:q});saveAtlasHistory();atlasInput.value='';
  const loading=document.createElement('div');loading.className='message atlas';loading.textContent='Thinking…';thread.appendChild(loading);thread.scrollTop=thread.scrollHeight;
  try{
    const res=await fetch('/api/atlas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:q,history:atlasHistory.slice(0,-1),context:location.pathname})});
    const data=await res.json();loading.remove();
    if(!res.ok||!data.ok)throw new Error(data.error||'Atlas is unavailable.');
    thread.insertAdjacentHTML('beforeend',`<div class="message atlas">${renderAtlasMarkdown(data.reply)}</div>`);
    atlasHistory.push({role:'model',text:data.reply});saveAtlasHistory();
    if(data.actions?.length){const wrap=document.createElement('div');wrap.className='atlas-actions';data.actions.forEach(a=>wrap.appendChild(atlasActionElement(a)));thread.appendChild(wrap)}
  }catch(e){loading.remove();thread.insertAdjacentHTML('beforeend',`<div class="message atlas"><p>Atlas is temporarily unavailable. ${esc(e.message)}</p></div>`)}
  thread.scrollTop=thread.scrollHeight;
}
atlasForm?.addEventListener('submit',e=>{e.preventDefault();askAtlas(atlasInput.value.trim())});
$$('[data-atlas-prompt]').forEach(b=>b.addEventListener('click',()=>askAtlas(b.dataset.atlasPrompt)));

/* Feedback */
$$('input[name="identity"]').forEach(r=>r.addEventListener('change',()=>$('#feedbackNameWrap')?.classList.toggle('hidden',$('input[name="identity"]:checked')?.value!=='named')));
$('#feedbackForm')?.addEventListener('submit',async e=>{
  e.preventDefault();const fd=new FormData(e.currentTarget),p=Object.fromEntries(fd.entries());p.anonymous=p.identity!=='named';
  const status=$('#feedbackStatus');status.textContent='Saving…';
  try{
    const res=await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});const data=await res.json();
    status.textContent=data.message||data.error;if(res.ok){showToast('Feedback saved. Thank you.');e.currentTarget.reset();$('#feedbackNameWrap')?.classList.add('hidden')}
  }catch{status.textContent='Unable to save feedback right now.'}
});

/* Staff Board */
const boardKey='mclw-demo-board-v9';
function renderPosts(){
  const feed=$('#boardFeed');if(!feed)return;let posts=[];try{posts=JSON.parse(localStorage.getItem(boardKey)||'[]')}catch{}
  posts.forEach(p=>feed.insertAdjacentHTML('beforeend',`<article class="board-post"><div class="post-meta"><strong>${esc(p.name||'Demo staff member')}</strong><span>Local demo · This device</span></div><p>${esc(p.body)}</p></article>`))
}
renderPosts();
$('#boardPostButton')?.addEventListener('click',()=>{
  const name=$('#boardName')?.value.trim(),msg=$('#boardMessage')?.value.trim();if(!msg)return showToast('Write a short post first.');
  let posts=[];try{posts=JSON.parse(localStorage.getItem(boardKey)||'[]')}catch{};posts.push({name:name||'Demo staff member',body:msg});localStorage.setItem(boardKey,JSON.stringify(posts));location.reload()
});

/* Local prototype editor */
(function(){
  const modal=$('#editorModal'),form=$('#editorForm'),kindInput=$('#editorKind'),titleInput=$('#editorItemTitle'),urlInput=$('#editorUrl'),descInput=$('#editorDescription'),fileInput=$('#editorFile'),urlWrap=$('#editorUrlWrap'),fileWrap=$('#editorFileWrap'),modalTitle=$('#editorTitle');
  const storeKey='mclw-v9-local-edits';
  function load(){try{return JSON.parse(localStorage.getItem(storeKey)||'[]')}catch{return[]}}
  function save(items){localStorage.setItem(storeKey,JSON.stringify(items))}
  function openEditor(kind){
    if(!modal||!form)return;form.reset();kindInput.value=kind;modalTitle.textContent='Add '+kind.charAt(0).toUpperCase()+kind.slice(1);
    urlWrap.style.display=kind==='link'?'grid':'none';fileWrap.style.display=kind==='file'?'grid':'none';modal.classList.add('open');modal.setAttribute('aria-hidden','false');titleInput.focus()
  }
  function closeEditor(){modal?.classList.remove('open');modal?.setAttribute('aria-hidden','true')}
  function render(){
    $$('.local-edit-item').forEach(x=>x.remove());
    for(const item of load()){
      const zone=$(`[data-zone="${item.zone}"]`)||$('[data-zone="updates"]');if(!zone)continue;
      const el=document.createElement(item.kind==='link'?'a':'article');el.className='local-edit-item';
      if(item.kind==='link'&&item.url){el.href=item.url;el.target='_blank';el.rel='noopener'}
      el.innerHTML=`<strong>${esc(item.title)}</strong>${item.description?`<small>${esc(item.description)}</small>`:''}${item.fileName?`<small>File: ${esc(item.fileName)}</small>`:''}<button type="button" class="local-edit-remove" data-remove-edit="${item.id}">Remove</button>`;
      zone.appendChild(el)
    }
    $$('[data-remove-edit]').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();save(load().filter(x=>x.id!==b.dataset.removeEdit));render();showToast('Demo item removed')}))
  }
  $$('[data-editor-add]').forEach(b=>b.addEventListener('click',()=>openEditor(b.dataset.editorAdd)));
  $('#editorClose')?.addEventListener('click',closeEditor);$('#editorCancel')?.addEventListener('click',closeEditor);modal?.addEventListener('click',e=>{if(e.target===modal)closeEditor()});
  form?.addEventListener('submit',e=>{
    e.preventDefault();const kind=kindInput.value;const zone=kind==='link'?'quick-links':kind==='update'?'updates':kind==='section'?'updates':kind==='folder'?'updates':kind==='file'?'updates':'updates';
    const item={id:String(Date.now()),kind,title:titleInput.value.trim(),url:urlInput.value.trim(),description:descInput.value.trim(),fileName:fileInput.files?.[0]?.name||'',zone};
    if(!item.title)return;const items=load();items.push(item);save(items);render();closeEditor();showToast(`${item.title} added to your local demo`)
  });
  $('[data-editor-reset]')?.addEventListener('click',()=>{if(confirm('Remove all prototype edits saved in this browser?')){localStorage.removeItem(storeKey);render();showToast('Local edits reset')}});
  $$('[data-edit-card]').forEach(b=>b.addEventListener('click',e=>{
    e.preventDefault();e.stopPropagation();const card=b.closest('[data-editable-card]');
    if(b.dataset.editCard==='title'){const h=card.querySelector('h3'),value=prompt('Demo branch label:',h.textContent);if(value){h.textContent=value;showToast('Demo label updated')}}
    else{showToast('Image replacement is represented in this public prototype. Production would open an authenticated upload workflow.')}
  }));
  render()
})();

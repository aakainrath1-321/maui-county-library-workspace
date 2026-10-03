(()=>{
const dialog=document.getElementById('wailukuPreviewDialog');if(!dialog)return;
const image=document.getElementById('wailukuPreviewImage'),title=document.getElementById('wailukuPreviewTitle'),label=document.getElementById('wailukuPreviewLabel'),open=document.getElementById('wailukuPreviewOpen');let trigger;
document.addEventListener('click',event=>{const button=event.target.closest('[data-file-preview]');if(!button)return;trigger=button;image.src=button.dataset.filePreview;image.alt=button.dataset.fileLabel+' of '+button.dataset.fileTitle;title.textContent=button.dataset.fileTitle;label.textContent=button.dataset.fileLabel+' · Saved thumbnail. Open the original in OneDrive for the latest version.';open.href=button.dataset.fileUrl;dialog.showModal();});
document.getElementById('wailukuPreviewClose').addEventListener('click',()=>dialog.close());
dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();});
dialog.addEventListener('close',()=>trigger?.focus());
})();

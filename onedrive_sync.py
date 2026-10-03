"""Owner-authorized, read-only Wailuku sync; state never belongs in GitHub."""
import base64, hashlib, io, json, os, sqlite3, threading, time, uuid
from pathlib import Path
from urllib.parse import quote, urlsplit
import requests
from cryptography.fernet import Fernet
from flask import abort, render_template, request, session, redirect, Response

SCOPE = ['https://graph.microsoft.com/Files.Read']
GRAPH = 'https://graph.microsoft.com/v1.0/'
ROOT_PATH = 'Wailuku Public Library Branch Master Folder'
class SyncError(Exception): pass

def graph_get(path, token):
    url = path if path.startswith('https://') else GRAPH + path
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != 'graph.microsoft.com' or not parsed.path.startswith('/v1.0/'):
        raise SyncError('Microsoft returned an unexpected paging address.')
    response = requests.get(url, headers={'Authorization':'Bearer '+token}, timeout=(5,25), allow_redirects=False)
    if response.status_code in (401,403): raise SyncError('Reconnect OneDrive, or ask HSPLS IT if Microsoft requires approval.')
    if response.status_code == 429: raise SyncError('Microsoft is busy. Sync will try again later.')
    if response.status_code == 404: raise SyncError('The source folder is unavailable. Check its location and permissions.')
    if response.status_code != 200: raise SyncError('Microsoft could not provide the folder. Sync will try again later.')
    return response.json()

def scan_folder(token, root_id=None):
    root = graph_get('me/drive/items/'+quote(root_id,safe='') if root_id else 'me/drive/root:/'+quote(ROOT_PATH,safe='/'), token)
    if 'folder' not in root: raise SyncError('The OneDrive source must be a folder.')
    drive = root['parentReference']['driveId']; count = 0; seen = set()
    def walk(item, trail, depth):
        nonlocal count
        if depth > 30 or item['id'] in seen: raise SyncError('The folder structure could not be safely read.')
        seen.add(item['id']); entries = []
        path = 'drives/'+quote(drive,safe='')+'/items/'+quote(item['id'],safe='')+'/children?$select=id,name,folder,file,webUrl,eTag,lastModifiedDateTime,remoteItem&$top=200'
        visited = set()
        while path:
            if path in visited: raise SyncError('Microsoft returned a repeated page.')
            visited.add(path); page = graph_get(path,token)
            for child in page.get('value',[]):
                count += 1
                if count > 20000: raise SyncError('The source folder exceeds the supported size.')
                # Shortcuts can leave the authorized source tree; do not traverse them.
                if child.get('remoteItem'): continue
                name = child['name']; relative = '/'.join(trail+[name])
                if 'folder' in child:
                    entries.append({'type':'folder','name':name,'children':walk(child,trail+[name],depth+1)})
                elif 'file' in child:
                    url = child.get('webUrl',''); u = urlsplit(url)
                    if u.scheme != 'https' or not (u.hostname or '').endswith('.sharepoint.com'): continue
                    key = hashlib.sha256((drive+'\0'+child['id']+'\0'+child.get('eTag','')).encode()).hexdigest()
                    ext = Path(name).suffix[1:].lower() or 'file'
                    entry = {'type':'file','name':name,'path':'wailuku-files/'+relative,'ext':ext,'onedrive_url':url,'drive_id':drive,'item_id':child['id'],'preview_key':key}
                    if ext in {'pdf','doc','docx','xls','xlsx','ppt','pptx','jpg','jpeg','png','gif','webp'}:
                        entry['preview']={'url':'/branch/wailuku/onedrive/preview/'+key,'label':'OneDrive thumbnail'}
                    entries.append(entry)
            path = page.get('@odata.nextLink')
        return sorted(entries,key=lambda e:(e['type']=='file',e['name'].casefold()))
    children = walk(root,[],0)
    catalog = {e['name']:e['children'] for e in children if e['type']=='folder'}
    loose = [e for e in children if e['type']=='file']
    if loose: catalog['Master Folder Files']=loose
    return root['id'], catalog

class SyncStore:
    def __init__(self, directory, key):
        self.directory = Path(directory).resolve(); self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path = self.directory/'onedrive-sync.sqlite'; self.cipher = Fernet(key.encode())
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS previews (key TEXT PRIMARY KEY, body BLOB NOT NULL)')
        os.chmod(self.path,0o600)
    def db(self): return sqlite3.connect(self.path,timeout=30)
    def read(self):
        with self.db() as db: row=db.execute('SELECT payload FROM state WHERE id=1').fetchone()
        return json.loads(self.cipher.decrypt(row[0].encode())) if row else {}
    def write(self,state):
        with self.db() as db: db.execute('INSERT OR REPLACE INTO state VALUES(1,?)',(self.cipher.encrypt(json.dumps(state).encode()).decode(),))
    def disconnect(self):
        with self.db() as db:
            db.execute('DELETE FROM state');db.execute('DELETE FROM previews')

class OneDriveSync:
    def __init__(self, app, base, auth):
        self.app=app; self.auth=auth; self.store=None; self.started=False; self.start_lock=threading.Lock()
        self.enabled=os.environ.get('ONEDRIVE_SYNC_ENABLED')=='1'
        self.owner=os.environ.get('ONEDRIVE_SYNC_OWNER_OID','').strip()
        try:
            if self.enabled:
                uuid.UUID(self.owner)
                directory=os.environ.get('ONEDRIVE_SYNC_DATA_DIR','')
                if not directory: raise ValueError('Set ONEDRIVE_SYNC_DATA_DIR to durable private storage.')
                resolved=Path(directory).resolve()
                if Path(base).resolve() in resolved.parents or resolved==Path(base).resolve(): raise ValueError('Sync storage must be outside the app source folder.')
                self.store=SyncStore(directory,os.environ.get('ONEDRIVE_SYNC_KEY',''))
                self.store.read() # Fail closed if the encryption key was changed.
        except Exception:
            self.store=None
        self.interval=max(60,int(os.environ.get('ONEDRIVE_SYNC_INTERVAL_SECONDS','300')))
        app.extensions['onedrive_sync']=self
        self.routes()
        @app.before_request
        def start_sync():
            if self.store and self.store.read().get('cache'): self.start_worker()
        @app.context_processor
        def sync_context():
            catalog=self.catalog()
            wanted={'Library Programming Spreadsheet.xlsx','Library Programming Checklist.xlsx','Outreach Checklist.pdf','Expense Tracker.xlsx','Library of Things.xlsx','Maui Community Resources.xlsx'}
            featured=[e for e in self.files(catalog) if e['name'] in wanted] if catalog is not None else None
            return {'onedrive_sync_owner':self.is_owner() and self.enabled,'live_wailuku_resources':featured}
    def is_owner(self): return session.get('auth_provider')=='microsoft' and session.get('staff_oid')==self.owner
    def catalog(self):
        if not self.store:return None
        return self.store.read().get('catalog')
    def save_connection(self,claims,cache):
        if not self.store or claims['oid']!=self.owner:raise SyncError('Only the configured source owner can connect OneDrive.')
        import fcntl
        with open(self.store.directory/'sync.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            previous=self.store.read()
            self.store.write({'cache':cache.serialize(),'catalog':previous.get('catalog'),'root_id':previous.get('root_id'),'last_sync':previous.get('last_sync'),'message':'Connected. The first sync is starting.'})
        self.start_worker()
    def start_worker(self):
        with self.start_lock:
            if self.started:return
            self.started=True
            threading.Thread(target=self.loop,daemon=True,name='wailuku-onedrive-sync').start()
    def loop(self):
        while True:
            try:self.sync_once()
            except Exception:self.app.logger.warning('Wailuku OneDrive sync could not complete.')
            time.sleep(self.interval)
    def client_token(self,state):
        import msal
        cache=msal.SerializableTokenCache();cache.deserialize(state['cache'])
        client=self.auth['client'](self.auth['config'](),cache)
        accounts=[a for a in client.get_accounts() if a.get('local_account_id')==self.owner and a.get('realm')==os.environ.get('MICROSOFT_TENANT_ID')]
        if len(accounts)!=1:raise SyncError('Reconnect the source owner’s OneDrive account.')
        result=client.acquire_token_silent(SCOPE,account=accounts[0]) or {}
        state['cache']=cache.serialize()
        if not result.get('access_token'):raise SyncError('Microsoft needs you to reconnect OneDrive.')
        return result['access_token']
    def sync_once(self):
        if not self.store:return
        import fcntl
        # One lock spans cache refresh + scan + atomic publish across gunicorn workers.
        with open(self.store.directory/'sync.lock','a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return
            state=self.store.read()
            if not state.get('cache'):return
            try:
                token=self.client_token(state)
                root,catalog=scan_folder(token,state.get('root_id'))
                state.update(root_id=root,catalog=catalog,last_sync=time.time(),message='OneDrive is connected. Resources update automatically.')
                self.store.write(state)
                keys={e['preview_key'] for e in self.files(catalog)}
                with self.store.db() as db:
                    for (key,) in db.execute('SELECT key FROM previews').fetchall():
                        if key not in keys:db.execute('DELETE FROM previews WHERE key=?',(key,))
            except (SyncError,requests.RequestException,ValueError,KeyError):
                state['message']='Sync could not finish. The last successful resources remain available. Reconnect OneDrive or check Microsoft access.'
                self.store.write(state)
    @staticmethod
    def files(catalog):
        def walk(entries):
            for entry in entries:
                if entry['type']=='file':yield entry
                else:yield from walk(entry.get('children',[]))
        for entries in catalog.values():yield from walk(entries)
    def routes(self):
        app=self.app
        @app.get('/branch/wailuku/onedrive/account')
        def onedrive_account():
            if session.get('auth_provider')!='microsoft':abort(403)
            return Response('Your Microsoft account object ID:\n'+session['staff_oid']+'\n',mimetype='text/plain')
        @app.get('/branch/wailuku/onedrive')
        def onedrive_settings():
            if not self.is_owner():abort(403)
            state=self.store.read() if self.store else {}
            return render_template('onedrive-sync.html',ready=bool(self.store),connected=bool(state.get('cache')),message=state.get('message','Not connected yet.'),last_sync=state.get('last_sync'))
        @app.post('/branch/wailuku/onedrive/connect')
        def onedrive_connect():
            if not self.is_owner():abort(403)
            if not self.store:abort(503)
            flow=self.auth['client'](self.auth['config']()).initiate_auth_code_flow(scopes=SCOPE,redirect_uri=self.auth['config']()['REDIRECT_URI'],response_mode='query',prompt='consent')
            session['microsoft_flow']=flow;session['microsoft_flow_started']=time.time();session['microsoft_next']='/branch/wailuku/onedrive';session['microsoft_sync_owner']=self.owner
            return redirect(flow['auth_uri'])
        @app.post('/branch/wailuku/onedrive/disconnect')
        def onedrive_disconnect():
            if not self.is_owner():abort(403)
            if self.store:
                import fcntl
                with open(self.store.directory/'sync.lock','a') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX);self.store.disconnect()
            return redirect('/branch/wailuku/onedrive')
        @app.get('/branch/wailuku/onedrive/preview/<key>')
        def onedrive_preview(key):
            if not self.store:abort(404)
            catalog=self.catalog() or {}
            item=next((e for e in self.files(catalog) if e.get('preview_key')==key),None)
            if not item:abort(404)
            with self.store.db() as db:row=db.execute('SELECT body FROM previews WHERE key=?',(key,)).fetchone()
            if row:return Response(row[0],mimetype='image/jpeg')
            try:
                import fcntl
                with open(self.store.directory/'sync.lock','a') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX)
                    state=self.store.read()
                    if not state.get('cache'):abort(404)
                    token=self.client_token(state);self.store.write(state)
                    data=graph_get('drives/'+quote(item['drive_id'],safe='')+'/items/'+quote(item['item_id'],safe='')+'/thumbnails',token)
                thumb=next((t.get('large') or t.get('medium') for t in data.get('value',[]) if t.get('large') or t.get('medium')),None)
                if not thumb:raise SyncError('No thumbnail available.')
                url=thumb['url'];u=urlsplit(url);host=u.hostname or ''
                if u.scheme!='https' or not any(host.endswith('.'+d) for d in ('sharepoint.com','1drv.com','onedrive.com','files.1drv.com','microsoft.com')):raise SyncError('Unexpected thumbnail host.')
                with requests.get(url,timeout=(5,20),stream=True,allow_redirects=False) as r:
                    if r.status_code!=200:raise SyncError('Thumbnail unavailable.')
                    body=bytearray()
                    for part in r.iter_content(65536):
                        body.extend(part)
                        if len(body)>8*1024*1024:raise SyncError('Thumbnail too large.')
                from PIL import Image
                with Image.open(io.BytesIO(body)) as image:
                    if image.width*image.height>20000000:raise SyncError('Thumbnail too large.')
                    image.thumbnail((1400,1400));out=io.BytesIO();image.convert('RGB').save(out,format='JPEG',quality=85);body=out.getvalue()
                with self.store.db() as db:db.execute('INSERT OR REPLACE INTO previews VALUES(?,?)',(key,body))
                return Response(body,mimetype='image/jpeg')
            except (SyncError,requests.RequestException,ValueError,KeyError,OSError):
                # Show a readable placeholder; the original file remains accessible.
                return Response('<svg xmlns="http://www.w3.org/2000/svg" width="360" height="240"><rect width="100%" height="100%" fill="#f4f5f1"/><text x="180" y="110" text-anchor="middle" fill="#456" font-size="18">Preview unavailable</text><text x="180" y="145" text-anchor="middle" fill="#456" font-size="14">Open the original in OneDrive</text></svg>',mimetype='image/svg+xml')

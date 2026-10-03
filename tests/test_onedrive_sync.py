import importlib.util, json, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch, Mock
from cryptography.fernet import Fernet
from flask import Flask
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from onedrive_sync import scan_folder, SyncError, SyncStore, OneDriveSync, graph_get

class SyncTests(unittest.TestCase):
 def test_scan_paging_and_removed_items(self):
  root={'id':'root','folder':{},'parentReference':{'driveId':'drive'}}
  folder={'id':'staff','name':'Staff','folder':{}}
  file={'id':'one','name':'old.pdf','file':{},'webUrl':'https://librarieshawaii-my.sharepoint.com/doc','eTag':'v1'}
  def response(path,token):
   if 'root:/' in path or path=='me/drive/items/root':return root
   if '/items/root/' in path:return {'value':[folder]}
   if '/items/staff/' in path:return {'value':[file], '@odata.nextLink':'https://graph.microsoft.com/v1.0/next'}
   if path.endswith('/next'):return {'value':[{'id':'shortcut','name':'private','remoteItem':{}}]}
   raise AssertionError(path)
  with patch('onedrive_sync.graph_get',side_effect=response):
   _,a=scan_folder('token');self.assertEqual(a['Staff'][0]['name'],'old.pdf')
   key=a['Staff'][0]['preview_key'];file['name']='new.pdf';file['eTag']='v2'
   _,b=scan_folder('token','root');self.assertEqual(b['Staff'][0]['name'],'new.pdf');self.assertNotEqual(key,b['Staff'][0]['preview_key'])
  with patch('onedrive_sync.graph_get',side_effect=[root,{'value':[]}]):self.assertEqual(scan_folder('token','root')[1],{})
 def test_paging_cannot_exfiltrate_token(self):
  with patch('onedrive_sync.requests.get') as network:
   with self.assertRaises(SyncError):graph_get('https://evil.example/next','secret')
   network.assert_not_called()
 def test_state_is_encrypted_and_survives_restart(self):
  with tempfile.TemporaryDirectory() as d:
   key=Fernet.generate_key().decode();store=SyncStore(d,key)
   store.write({'cache':'refresh-token-secret','catalog':{}})
   self.assertNotIn(b'refresh-token-secret',store.path.read_bytes())
   self.assertEqual(SyncStore(d,key).read()['cache'],'refresh-token-secret')
   store.disconnect();self.assertEqual(store.read(),{})
 def test_failure_does_not_publish_partial_listing(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'ONEDRIVE_SYNC_ENABLED':'1','ONEDRIVE_SYNC_OWNER_OID':'11111111-1111-1111-1111-111111111111','ONEDRIVE_SYNC_DATA_DIR':d,'ONEDRIVE_SYNC_KEY':Fernet.generate_key().decode()}):
   app=Flask(__name__);app.secret_key='test';sync=OneDriveSync(app,ROOT, {})
   sync.store.write({'cache':'cache','catalog':{'Old':[]}})
   with patch.object(sync,'client_token',return_value='token'),patch('onedrive_sync.scan_folder',side_effect=SyncError('429')):sync.sync_once()
   self.assertEqual(sync.catalog(),{'Old':[]})
 def test_new_top_level_folder_and_atlas_navigation(self):
  # Disabled sync keeps baseline behavior; fake catalog simulates a completed scan.
  import app as site
  site.app.config['TESTING']=True
  sync=site.app.extensions['onedrive_sync']
  catalog={'New Project':[{'type':'file','name':'New Document.pdf','ext':'pdf','onedrive_url':'https://librarieshawaii-my.sharepoint.com/doc'}]}
  with patch.object(sync,'catalog',return_value=catalog):
   sections=site.current_wailuku_sections();self.assertEqual(len(sections),1)
   url='/branch/wailuku/'+sections[0]['slug']
   self.assertTrue(site.atlas_navigation_is_valid(url))
   with site.app.test_request_context(url):
    html=site.section('wailuku',sections[0]['slug']);self.assertIn('New Document.pdf',html)
   self.assertTrue(any('New Document' in i['label'] for i in site.flatten_nodes()))
 def test_nonowner_cannot_manage_connection(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'ONEDRIVE_SYNC_ENABLED':'1','ONEDRIVE_SYNC_OWNER_OID':'11111111-1111-1111-1111-111111111111','ONEDRIVE_SYNC_DATA_DIR':d,'ONEDRIVE_SYNC_KEY':Fernet.generate_key().decode()}):
   app=Flask(__name__);app.secret_key='test';sync=OneDriveSync(app,ROOT,{})
   c=app.test_client()
   self.assertEqual(c.post('/branch/wailuku/onedrive/connect').status_code,403)
   self.assertEqual(c.post('/branch/wailuku/onedrive/disconnect').status_code,403)


class AuthorizationTests(unittest.TestCase):
 def test_owner_callback_stores_no_tokens_in_cookie_and_rejects_wrong_account(self):
  import app as site, msal, jwt
  from cryptography.hazmat.primitives.asymmetric import rsa
  owner='11111111-1111-1111-1111-111111111111';tenant='22222222-2222-2222-2222-222222222222';client='33333333-3333-3333-3333-333333333333'
  key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
  sync=site.app.extensions['onedrive_sync'];old=(sync.owner,sync.store,sync.enabled)
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'MICROSOFT_TENANT_ID':tenant,'MICROSOFT_CLIENT_ID':client,'MICROSOFT_CLIENT_SECRET':'testsecret','MICROSOFT_REDIRECT_URI':'http://localhost/auth/callback'}):
   sync.owner=owner;sync.enabled=True;sync.store=SyncStore(d,Fernet.generate_key().decode())
   try:
    def callback(oid):
     c=site.app.test_client()
     with c.session_transaction() as s:
      s.update(auth_provider='microsoft',tenant_id=tenant,client_id=client,staff_oid=owner,account_member=True,expires_at=time.time()+3600,csrf='csrf',microsoft_flow={'state':'state','nonce':'nonce'},microsoft_flow_started=time.time(),microsoft_next='/branch/wailuku/onedrive',microsoft_sync_owner=owner)
     claims={'oid':oid,'tid':tenant,'acct':0,'aud':client,'iss':'https://login.microsoftonline.com/'+tenant+'/v2.0','iat':int(time.time()),'exp':int(time.time()+3600),'nonce':'nonce'}
     result={'id_token':jwt.encode(claims,key,algorithm='RS256'),'scope':'Files.Read','access_token':'never-cookie-secret'}
     with patch('msal.ConfidentialClientApplication') as factory,patch('jwt.PyJWKClient') as jwks,patch.object(sync,'start_worker'):
      factory.return_value.acquire_token_by_auth_code_flow.return_value=result
      jwks.return_value.get_signing_key_from_jwt.return_value.key=key.public_key()
      response=c.get('/auth/callback?state=state&code=code')
     return c,response
    c,r=callback('44444444-4444-4444-4444-444444444444');self.assertEqual(r.status_code,403);self.assertEqual(sync.store.read(),{})
    c,r=callback(owner);self.assertEqual(r.status_code,302);self.assertIn('cache',sync.store.read())
    with c.session_transaction() as s:self.assertNotIn('access_token',s);self.assertNotIn('cache',s)
    self.assertEqual(c.post('/branch/wailuku/onedrive/disconnect').status_code,403)
    with patch.object(sync,'start_worker'):
     self.assertEqual(c.post('/branch/wailuku/onedrive/disconnect',data={'csrf_token':'old-csrf'}).status_code,403) # old CSRF rotates after callback
     with c.session_transaction() as s:csrf=s['csrf']
     self.assertEqual(c.post('/branch/wailuku/onedrive/disconnect',data={'csrf_token':csrf}).status_code,302)
    self.assertEqual(sync.store.read(),{})
   finally:sync.owner,sync.store,sync.enabled=old

if __name__=='__main__':unittest.main()

"""Staff authentication. Password hashes only; production configuration is environment-owned."""
import os, json, secrets, hashlib, hmac, time
from pathlib import Path
from datetime import timedelta
from urllib.parse import urlsplit
from collections import defaultdict, deque
from flask import request, session, redirect, url_for, render_template, jsonify, abort
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from uuid import UUID

def configure_auth(app, base):
    production=bool(os.environ.get('RENDER')) or os.environ.get('WORKSPACE_PRODUCTION')=='1'
    secret=os.environ.get('SECRET_KEY','')
    if not production and len(secret)<32:
        keyfile=base/'.local-session-key'
        if not keyfile.exists():
            fd=os.open(keyfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:f.write(secrets.token_hex(32))
        secret=keyfile.read_text().strip()
    app.config.update(SECRET_KEY=secret or secrets.token_hex(32),SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=production or os.environ.get('AUTH_COOKIE_SECURE')=='1',PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
    if production:app.wsgi_app=ProxyFix(app.wsgi_app,x_proto=1,x_host=0,x_for=0)
    attempts=defaultdict(deque)
    dummy_hash=generate_password_hash(secrets.token_hex(24))
    def users():
        try:
            raw=os.environ.get('AUTH_USERS_JSON')
            if raw is None and not production:
                p=base/'.local-auth.json';raw=p.read_text() if p.exists() else '{}'
            data=json.loads(raw or '{}')
            return {k.lower():v for k,v in data.items() if isinstance(k,str) and isinstance(v,str) and v.startswith(('scrypt:','pbkdf2:'))}
        except (OSError,ValueError,AttributeError):return {}
    def microsoft_config():
        values={k:os.environ.get('MICROSOFT_'+k,'').strip() for k in ('CLIENT_ID','TENANT_ID','CLIENT_SECRET','REDIRECT_URI')}
        try:
            UUID(values['CLIENT_ID']);UUID(values['TENANT_ID'])
            uri=urlsplit(values['REDIRECT_URI'])
            valid_uri=uri.scheme=='https' or (not production and uri.scheme=='http' and uri.hostname in {'localhost','127.0.0.1'})
            if not values['CLIENT_SECRET'] or not valid_uri or not uri.netloc or uri.path!='/auth/callback' or uri.query or uri.fragment or uri.username:return None
            return values
        except ValueError:return None
    def microsoft_enabled():return microsoft_config() is not None
    def local_enabled():return not (production and any(os.environ.get('MICROSOFT_'+k) for k in ('CLIENT_ID','TENANT_ID','CLIENT_SECRET','REDIRECT_URI'))) and bool(users())
    def configured():return (microsoft_enabled() or local_enabled()) and (not production or len(secret)>=32)
    def microsoft_client(config):
        import msal
        return msal.ConfidentialClientApplication(config['CLIENT_ID'],authority='https://login.microsoftonline.com/'+config['TENANT_ID'],client_credential=config['CLIENT_SECRET'])
    def csrf():
        if 'csrf' not in session:session['csrf']=secrets.token_urlsafe(32)
        return session['csrf']
    app.jinja_env.globals['workspace_csrf']=csrf
    def safe_next(value):
        v=value or '/branch/wailuku';parsed=urlsplit(v)
        return v if v.startswith('/') and not v.startswith('//') and not parsed.netloc and not parsed.scheme and '\\' not in v else '/branch/wailuku'
    def authenticated():
        if session.get('auth_provider')=='microsoft':
            config=microsoft_config()
            return bool(config and session.get('tenant_id')==config['TENANT_ID'] and session.get('client_id')==config['CLIENT_ID'] and session.get('staff_oid') and session.get('account_member') is True and time.time()<session.get('expires_at',0))
        if not local_enabled():return False
        name=session.get('staff_user');stored=users().get(name)
        return bool(stored and hmac.compare_digest(session.get('credential_version',''),hashlib.sha256(stored.encode()).hexdigest()) and time.time()<session.get('expires_at',0))
    @app.before_request
    def enforce_auth():
        if production and not request.is_secure:return 'HTTPS is required.',400
        if request.endpoint in {'staff_login','workspace_service_worker','microsoft_start','microsoft_callback'}:return None
        if not configured():return (jsonify(error='Staff sign-in has not been configured.'),503) if request.path.startswith(('/api/','/static/')) else redirect(url_for('staff_login'))
        if not authenticated():
            # Preserve the login form token across unauthenticated asset requests.
            for key in ('staff_user', 'credential_version', 'expires_at', 'auth_provider', 'staff_oid', 'tenant_id', 'client_id', 'account_member'):
                session.pop(key, None)
            if request.path.startswith(('/api/','/static/')):return jsonify(error='Please sign in to the staff workspace.'),401
            return redirect(url_for('staff_login',next=request.full_path.rstrip('?')))
        if request.method not in {'GET','HEAD','OPTIONS'}:
            token=request.headers.get('X-CSRF-Token') or request.form.get('csrf_token','')
            if not token or not hmac.compare_digest(token,session.get('csrf','')):return jsonify(error='Refresh the page and try again.'),403
    @app.after_request
    def security_headers(response):
        response.headers['Cache-Control']='no-store, private'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='SAMEORIGIN'
        response.headers['Referrer-Policy']='same-origin'
        if production:response.headers['Strict-Transport-Security']='max-age=31536000'
        return response
    @app.get('/service-worker.js',endpoint='workspace_service_worker')
    def retire_worker():
        return app.response_class("self.addEventListener('install',()=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('mclw-')).map(k=>caches.delete(k)))).then(()=>self.registration.unregister()).then(()=>self.clients.claim())));",mimetype='application/javascript')
    @app.route('/login',methods=['GET','POST'],endpoint='staff_login')
    def login():
        next_path=safe_next(request.values.get('next'))
        if authenticated():return redirect(next_path)
        error=None
        if request.method=='POST':
            token=request.form.get('csrf_token','')
            if not token or not hmac.compare_digest(token,session.get('csrf','')):abort(403)
            name=request.form.get('username','').strip().lower();password=request.form.get('password','')
            bucket=attempts[name]
            now=time.time()
            while bucket and bucket[0]<now-900:bucket.popleft()
            if len(bucket)>=5:error='Too many attempts. Please wait 15 minutes and try again.'
            elif not configured() or not local_enabled():error='Use your HSPLS Microsoft account to sign in.' if microsoft_enabled() else 'Staff sign-in has not been configured yet.'
            else:
                stored=users().get(name);valid=check_password_hash(stored or dummy_hash,password)
                if stored and valid:
                    bucket.clear();session.clear();session.permanent=True
                    session['staff_user']=name;session['credential_version']=hashlib.sha256(stored.encode()).hexdigest();session['expires_at']=now+8*3600;csrf()
                    return redirect(next_path)
                bucket.append(now);error='The username or password was not recognized.'
        return render_template('login.html',error=error,configured=configured(),next_path=next_path,microsoft_enabled=microsoft_enabled(),local_enabled=local_enabled()),429 if error and error.startswith('Too many') else 200

    def microsoft_error(message,status):
        return render_template('login.html',error=message,configured=configured(),next_path='/branch/wailuku',microsoft_enabled=microsoft_enabled(),local_enabled=local_enabled()),status

    @app.post('/auth/microsoft',endpoint='microsoft_start')
    def microsoft_start():
        config=microsoft_config()
        if not config or not configured():return microsoft_error('Microsoft sign-in is not configured yet.',503)
        token=request.form.get('csrf_token','')
        if not token or not hmac.compare_digest(token,session.get('csrf','')):return microsoft_error('Refresh this page and try again.',400)
        try:
            # MSAL adds OpenID scopes, state, nonce and PKCE. No Graph permissions.
            flow=microsoft_client(config).initiate_auth_code_flow(scopes=[],redirect_uri=config['REDIRECT_URI'],response_mode='query',prompt='select_account')
            if not flow.get('auth_uri'):raise ValueError('Missing authorization URL')
            session['microsoft_flow']=flow
            session['microsoft_flow_started']=time.time()
            session['microsoft_next']=safe_next(request.form.get('next'))
            return redirect(flow['auth_uri'])
        except Exception:
            app.logger.warning('Microsoft sign-in could not start.')
            return microsoft_error('Microsoft sign-in is temporarily unavailable. Please try again.',503)

    @app.get('/auth/callback',endpoint='microsoft_callback')
    def microsoft_callback():
        config=microsoft_config()
        flow=session.pop('microsoft_flow',None)
        started=session.pop('microsoft_flow_started',0)
        destination=safe_next(session.pop('microsoft_next',None))
        if not config or not configured():return microsoft_error('Microsoft sign-in is not configured yet.',503)
        state=request.args.get('state','')
        if not flow or time.time()-started>600 or not state or not hmac.compare_digest(state,flow.get('state','')):return microsoft_error('Sign-in expired. Please start again.',400)
        try:
            result=microsoft_client(config).acquire_token_by_auth_code_flow(flow,request.args)
            if result.get('error') or not result.get('id_token'):return microsoft_error('Microsoft could not complete sign-in. Try again, or contact HSPLS IT if approval is required.',401)
            # Independently validate the signature as well as MSAL's nonce checks.
            import jwt
            jwks=jwt.PyJWKClient('https://login.microsoftonline.com/'+config['TENANT_ID']+'/discovery/v2.0/keys',timeout=10)
            key=jwks.get_signing_key_from_jwt(result['id_token']).key
            claims=jwt.decode(result['id_token'],key,algorithms=['RS256'],audience=config['CLIENT_ID'],issuer='https://login.microsoftonline.com/'+config['TENANT_ID']+'/v2.0',options={'require':['exp','iat','iss','aud','tid','oid','nonce']})
            if claims.get('tid')!=config['TENANT_ID'] or not claims.get('oid'):return microsoft_error('This workspace requires an HSPLS work account.',403)
            if str(claims.get('acct'))!='0':return microsoft_error('An HSPLS staff member account is required. If you are staff, ask the app owner to enable the Microsoft acct claim.',403)
            session.clear();session.permanent=True
            session.update(auth_provider='microsoft',tenant_id=config['TENANT_ID'],client_id=config['CLIENT_ID'],staff_oid=claims['oid'],account_member=True,expires_at=min(time.time()+8*3600,claims['exp']))
            csrf()
            return redirect(destination)
        except Exception:
            app.logger.warning('Microsoft sign-in validation failed.')
            return microsoft_error('Sign-in could not be verified. Please start again.',401)
    @app.post('/logout',endpoint='staff_logout')
    def logout():
        session.clear();return redirect(url_for('staff_login'))

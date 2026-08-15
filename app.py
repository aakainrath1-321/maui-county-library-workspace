import os, sqlite3, json, re, time
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, render_template, request, jsonify, abort

BASE_DIR=Path(__file__).resolve().parent
DB_PATH=Path(os.environ.get('WORKSPACE_DB_PATH', BASE_DIR/'workspace.db'))
app=Flask(__name__)
app.config['SECRET_KEY']=os.environ.get('SECRET_KEY','prototype-only-change-me')

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
ATLAS_RETRY_ATTEMPTS = int(os.environ.get("ATLAS_RETRY_ATTEMPTS", "2"))
ATLAS_MAX_HISTORY = 16

ATLAS_SYSTEM_PROMPT = """
You are Atlas, the embedded workspace intelligence for the Maui County Library Workspace Prototype.

IDENTITY AND PURPOSE
- Support HSPLS staff and users by helping them navigate, understand, organize, and interact with the Maui County Library Workspace.
- Be warm, professional, concise, grounded, and practical.
- You are not a mascot and not a generic customer-service bot.
- Never begin with canned phrases such as "Certainly!", "As an AI...", or "Great question!".
- You may have normal conversation, brainstorm, explain design choices, and help users think through staff-workspace problems.

PROTOTYPE BOUNDARIES
- This public prototype intentionally contains no restricted operational HSPLS content.
- Never imply access to internal documents, patron records, staff records, passwords, state systems, OneDrive, SharePoint, email, or private databases.
- If asked about unavailable internal content, say it is not present in this prototype and offer help with structure, placement, navigation, or planning.

WORKSPACE KNOWLEDGE
- Eight libraries: Hana Public/School Library, Kahului Public Library, Kihei Public Library, Lahaina Public Library, Lānaʻi Public/School Library, Makawao Public Library, Molokaʻi Public Library, and Wailuku Public Library.
- Every branch uses Management, Operations, Services, and Communications.
- Management: Agenda & Calendar; Service Framework & Strategic Plan; Budget & Finance; Staff Information; In/Out Sheets.
- Operations: Building Layout & Spaces; Policies & Procedures; Training & Tutorials; Systems & Digital Infrastructure.
- Services: Collection Development; Community Engagement & Programming; Surveys & Feedback.
- Collection Development: Packing Lists & Invoices (2025, 2026); Order Lists (Adult, Young Adult, Juvenile, Audiovisual); Licensing & Copyright.
- Communications: Marketing (Newsletters; Flyers & Posters); Website Updates.

SITE INTERACTION
When useful, propose safe UI actions at the very end of your response using one or more of these exact blocks:
[[ACTION:{"type":"navigate","label":"Open Wailuku Policies","url":"/branch/wailuku/operations#policies-procedures"}]]
[[ACTION:{"type":"open_feedback","label":"Open feedback"}]]
[[ACTION:{"type":"enter_edit_mode","label":"Enter Edit Mode"}]]

Do not explain the action syntax to the user.
Only use routes that exist in the prototype.
Do not invent destructive, privileged, or external-system actions.

CONVERSATION
- Use history so follow-ups such as "take me there" and "what about Lahaina?" make sense.
- Be capable of ordinary conversation, not just navigation.
- When asked where something belongs, explain the hierarchy clearly and optionally provide a navigation action.
"""

def atlas_workspace_context(current_path):
    path = current_path or "/"
    context = {"path": path, "branch": None, "section": None}
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "branch":
        b = get_branch(parts[1])
        if b:
            context["branch"] = b["name"]
    if len(parts) >= 3 and parts[0] == "branch":
        s = get_section(parts[2])
        if s:
            context["section"] = s["name"]
    return context

def parse_atlas_actions(text):
    actions = []
    pattern = re.compile(r'\[\[ACTION:(\{.*?\})\]\]')
    for raw in pattern.findall(text or ""):
        try:
            action = json.loads(raw)
            if action.get("type") in {"navigate", "open_feedback", "enter_edit_mode"}:
                actions.append(action)
        except Exception:
            pass
    return pattern.sub("", text or "").strip(), actions


BRANCHES=[
 {'slug':'hana','name':'Hana Public/School Library','island':'Maui','photo':'hana.png','logo':'hana.png','model':{'type':'meshy','label':'Hana Public/School Library','url':'https://www.meshy.ai/3d-models/Library-with-Palm-Trees-019fe2df-c25a-7696-9b1e-9bb4b2d8a1b5?utm_medium=referral-program&utm_source=meshy&utm_content=Y383N5&share_type=3d-models'}},
 {'slug':'kahului','name':'Kahului Public Library','island':'Maui','photo':'kahului.jpg','logo':'kahului.png','model':None},
 {'slug':'kihei','name':'Kihei Public Library','island':'Maui','photo':'kihei.jpg','logo':'kihei.png','model':None},
 {'slug':'lahaina','name':'Lahaina Public Library','island':'Maui','photo':'lahaina.jpg','logo':'lahaina.png','model':{'type':'sketchfab','label':'Lahaina Public Library','uid':'0e8605eac6d6465a8f6582bde7d99720'}},
 {'slug':'lanai','name':'Lānaʻi Public/School Library','island':'Lānaʻi','photo':'lanai.jpg','logo':'lanai.png','model':None},
 {'slug':'makawao','name':'Makawao Public Library','island':'Maui','photo':'makawao.jpg','logo':'makawao.png','model':None},
 {'slug':'molokai','name':'Molokaʻi Public Library','island':'Molokaʻi','photo':'molokai.jpg','logo':'molokai.png','model':None},
 {'slug':'wailuku','name':'Wailuku Public Library','island':'Maui','photo':'wailuku.jpg','logo':'wailuku.png','model':None},
]
SECTIONS=[
 {'slug':'management','name':'Management','description':'Administration, planning, staff coordination, budgeting, and strategic direction.','items':[
   {'slug':'agenda-calendar','name':'Agenda & Calendar'},
   {'slug':'service-framework-strategic-plan','name':'Service Framework & Strategic Plan'},
   {'slug':'budget-finance','name':'Budget & Finance'},
   {'slug':'staff-information','name':'Staff Information','children':[{'slug':'in-out-sheets','name':'In/Out Sheets'}]},]},
 {'slug':'operations','name':'Operations','description':'Daily branch operations, spaces, procedures, systems, and staff development.','items':[
   {'slug':'building-layout-spaces','name':'Building Layout & Spaces'},
   {'slug':'policies-procedures','name':'Policies & Procedures'},
   {'slug':'training-tutorials','name':'Training & Tutorials'},
   {'slug':'systems-digital-infrastructure','name':'Systems & Digital Infrastructure'},]},
 {'slug':'services','name':'Services','description':'Collections, programming, community engagement, and feedback.','items':[
   {'slug':'collection-development','name':'Collection Development','children':[
      {'slug':'packing-lists-invoices','name':'Packing Lists & Invoices','children':[{'slug':'2025','name':'2025'},{'slug':'2026','name':'2026'}]},
      {'slug':'order-lists','name':'Order Lists','children':[{'slug':'adult-collection','name':'Adult Collection'},{'slug':'young-adult-collection','name':'Young Adult Collection'},{'slug':'juvenile-collection','name':'Juvenile Collection'},{'slug':'audiovisual-collection','name':'Audiovisual Collection'}]},
      {'slug':'licensing-copyright','name':'Licensing & Copyright'}]},
   {'slug':'community-engagement-programming','name':'Community Engagement & Programming'},
   {'slug':'surveys-feedback','name':'Surveys & Feedback'},]},
 {'slug':'communications','name':'Communications','description':'Marketing, branch communications, newsletters, and web updates.','items':[
   {'slug':'marketing','name':'Marketing','children':[{'slug':'newsletters','name':'Newsletters'},{'slug':'flyers-posters','name':'Flyers & Posters'}]},
   {'slug':'website-updates','name':'Website Updates'},]},
]
QUICK_LINKS=[
 {'label':'HSPLS Website','url':'https://www.librarieshawaii.org/','type':'Public website'},
 {'label':'Branch Directory','url':'https://www.librarieshawaii.org/branch/','type':'Library pages'},
 {'label':'Prototype Guide','url':'/prototype','type':'About this prototype'},
]
SAMPLE_POSTS=[
 {'branch':'Maui County','name':'Workspace Team','time':'Prototype','body':'Welcome to the Staff Board. In a production workspace, branches could share updates, questions, useful resources, and ideas here.'},
 {'branch':'Kihei','name':'Sample Staff Post','time':'Demo','body':'This is an example of a branch sharing a programming idea with colleagues across Maui County.'},
]

def db():
 c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c

def init_db():
 c=db(); c.execute('''CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, display_name TEXT NOT NULL, is_anonymous INTEGER NOT NULL DEFAULT 1, branch TEXT, category TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL)'''); c.commit(); c.close()
init_db()

def get_branch(slug): return next((b for b in BRANCHES if b['slug']==slug),None)
def get_section(slug): return next((s for s in SECTIONS if s['slug']==slug),None)

def flatten_nodes():
 nodes=[]
 for b in BRANCHES:
  nodes.append({'label':b['name'],'url':f"/branch/{b['slug']}",'keywords':f"{b['name']} branch library {b['island']}"})
  for s in SECTIONS:
   nodes.append({'label':f"{b['name']} — {s['name']}",'url':f"/branch/{b['slug']}/{s['slug']}",'keywords':f"{b['name']} {s['name']} {s['description']}"})
   def walk(items,trail):
    for item in items:
     label=' › '.join(trail+[item['name']])
     nodes.append({'label':f"{b['name']} — {label}",'url':f"/branch/{b['slug']}/{s['slug']}#{item['slug']}",'keywords':f"{b['name']} {label}"})
     walk(item.get('children',[]),trail+[item['name']])
   walk(s['items'],[s['name']])
 return nodes
SEARCH_INDEX=flatten_nodes()

@app.context_processor
def inject_globals(): return {'branches':BRANCHES,'sections':SECTIONS}
@app.get('/')
def home(): return render_template('home.html',quick_links=QUICK_LINKS,sample_posts=SAMPLE_POSTS)
@app.get('/prototype')
def prototype(): return render_template('prototype.html')
@app.get('/authentication')
def authentication(): return render_template('authentication.html')
@app.get('/branch/<branch_slug>')
def branch(branch_slug):
 b=get_branch(branch_slug)
 if not b: abort(404)
 return render_template('branch.html',branch=b)
@app.get('/branch/<branch_slug>/<section_slug>')
def section(branch_slug,section_slug):
 b,s=get_branch(branch_slug),get_section(section_slug)
 if not b or not s: abort(404)
 return render_template('section.html',branch=b,section=s)
@app.get('/api/search')
def search():
 q=(request.args.get('q') or '').strip().lower()
 if not q: return jsonify([])
 terms=[t for t in q.split() if t]; scored=[]
 for item in SEARCH_INDEX:
  hay=(item['label']+' '+item['keywords']).lower(); score=sum(3 if t in item['label'].lower() else 1 for t in terms if t in hay)
  if score: scored.append((score,item))
 scored.sort(key=lambda x:(-x[0],x[1]['label']))
 return jsonify([i for _,i in scored[:10]])
@app.post('/api/feedback')
def feedback():
 d=request.get_json(silent=True) or request.form; anonymous=str(d.get('anonymous','true')).lower() in {'true','1','yes','on'}
 name=(d.get('name') or '').strip(); category=(d.get('category') or 'General Feedback').strip()[:80]; branch=(d.get('branch') or '').strip()[:80]; message=(d.get('message') or '').strip()
 if len(message)<3: return jsonify({'ok':False,'error':'Please enter a little more detail.'}),400
 display='Anonymous' if anonymous else (name or 'Staff member')
 c=db(); c.execute('INSERT INTO feedback(display_name,is_anonymous,branch,category,message,created_at) VALUES(?,?,?,?,?,?)',(display,1 if anonymous else 0,branch,category,message,datetime.now(timezone.utc).isoformat())); c.commit(); c.close()
 return jsonify({'ok':True,'message':'Thank you. Your feedback was saved.'})
@app.post('/api/atlas')
def atlas():
    payload = request.get_json(silent=True) or {}
    user_input = (payload.get("message") or "").strip()
    history = payload.get("history") or []
    current_path = (payload.get("context") or "/").strip()

    if not user_input:
        return jsonify({"ok": False, "error": "Message is required."}), 400

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return jsonify({
            "ok": False,
            "error": "Atlas is ready for Gemini, but GEMINI_API_KEY is not configured."
        }), 503

    try:
        from google import genai
        from google.genai import types
    except Exception:
        return jsonify({
            "ok": False,
            "error": "Google Gen AI SDK is missing. Run: py -m pip install -r requirements.txt"
        }), 500

    page_context = atlas_workspace_context(current_path)
    context_text = (
        "\n\nCURRENT WORKSPACE CONTEXT\n"
        f"- Current path: {page_context['path']}\n"
        f"- Current branch: {page_context['branch'] or 'Countywide / none'}\n"
        f"- Current section: {page_context['section'] or 'None'}\n"
    )

    contents = []
    for item in history[-ATLAS_MAX_HISTORY:]:
        role = "model" if item.get("role") == "model" else "user"
        text = (item.get("text") or "").strip()
        if text:
            contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    contents.append(types.Content(role="user", parts=[types.Part(text=user_input)]))

    client = genai.Client(api_key=api_key)
    model_candidates = []
    for model_name in (GEMINI_MODEL, GEMINI_FALLBACK_MODEL):
        if model_name and model_name not in model_candidates:
            model_candidates.append(model_name)

    last_error = None
    for model_name in model_candidates:
        for attempt in range(ATLAS_RETRY_ATTEMPTS):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=ATLAS_SYSTEM_PROMPT + context_text,
                        temperature=0.55,
                    ),
                )
                raw_text = (response.text or "").strip()
                clean_text, actions = parse_atlas_actions(raw_text)
                if not clean_text:
                    clean_text = "I’m here. Ask me about the workspace, where something belongs, or just talk through an idea with me."
                return jsonify({
                    "ok": True,
                    "reply": clean_text,
                    "actions": actions,
                    "model": model_name,
                    "context": page_context
                })
            except Exception as exc:
                last_error = exc
                msg = str(exc).upper()
                transient = any(code in msg for code in ("503", "UNAVAILABLE", "HIGH DEMAND", "429", "RESOURCE_EXHAUSTED"))
                if transient and attempt < ATLAS_RETRY_ATTEMPTS - 1:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                break

    return jsonify({
        "ok": False,
        "error": "Atlas is temporarily busy. Gemini is experiencing high demand, so please try again in a moment.",
        "technical_detail": str(last_error) if last_error else "Unknown Gemini error"
    }), 503

@app.get('/api/atlas/health')
def atlas_health():
    status = {
        "gemini_api_key_configured": bool(os.environ.get("GEMINI_API_KEY")),
        "gemini_model": GEMINI_MODEL,
        "gemini_fallback_model": GEMINI_FALLBACK_MODEL,
        "database": "unknown",
        "workspace_context": "ok"
    }
    try:
        conn = db()
        conn.execute("SELECT 1")
        conn.close()
        status["database"] = "ok"
    except Exception as exc:
        status["database"] = "error: " + str(exc)

    if request.args.get("live") == "1" and status["gemini_api_key_configured"]:
        try:
            from google import genai
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            test = client.models.generate_content(
                model=GEMINI_MODEL,
                contents="Reply with exactly: Atlas online"
            )
            status["gemini_live_test"] = (test.text or "").strip()
        except Exception as exc:
            status["gemini_live_test"] = "error: " + str(exc)

    return jsonify(status)

if __name__=='__main__': app.run(debug=os.environ.get('FLASK_DEBUG')=='1')

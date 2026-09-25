import os, sqlite3, json, re, time
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, render_template, request, jsonify, abort, Response

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
- Help HSPLS staff navigate, understand, organize, and interact with this prototype.
- Be warm, professional, concise, grounded, and practical.
- Never imply access to private HSPLS systems, patron/staff records, OneDrive, SharePoint, email, or restricted content.
- This public prototype contains only approved prototype content and packaged demonstration resources.

CURRENT INFORMATION ARCHITECTURE
- Eight branches are represented: Hana, Kahului, Kihei, Lahaina, Lānaʻi, Makawao, Molokaʻi, and Wailuku.
- Non-Wailuku branches retain the shared prototype areas Management, Operations, Services, and Communications.
- Wailuku is different and uses the current work-first structure below. NEVER send Wailuku users to the old Management/Operations/Services/Communications routes.
- Wailuku areas, with exact routes:
  01 Staff — /branch/wailuku/staff
  02 Patron Services — /branch/wailuku/patron-services
  03 Collections — /branch/wailuku/collections
  04 Programs & Outreach — /branch/wailuku/programs-outreach
  05 Bookmobile — /branch/wailuku/bookmobile
  06 Facilities — /branch/wailuku/facilities
  07 Technology — /branch/wailuku/technology
  08 Safety & Security — /branch/wailuku/safety-security
  09 Finance & Purchasing — /branch/wailuku/finance-purchasing
  10 Branch Management — /branch/wailuku/branch-management
  11 Communications — /branch/wailuku/communications
- Wailuku home — /branch/wailuku

WAILUKU FILING LOGIC
- File by the function that owns the record, not by employee or file type.
- Procedures, forms, and templates live with their function; there is no master procedures/forms folder.
- Bookmobile holds Bookmobile-specific operations only. Collections go to Collections; staff records to Staff; programming to Programs & Outreach; financial transactions to Finance & Purchasing.
- Finance owns the transaction; the operational area owns the underlying work/decision.
- Communications owns finished public-facing communications.
- Technology owns equipment/systems; Patron Services owns the patron-facing service.
- Facilities owns physical property; Safety & Security owns risk, response, incidents, and security procedures.
- Branch Management is for branch-wide managerial records, including daily operations, deadlines, goals/planning, statistics/reports, policies, official correspondence, records management, assessments, and surveys.
- Do not invent folders or claim a resource exists when it is not present in the prototype.

NAVIGATION SAFETY
- Only propose navigation actions using a route that exists in the CURRENT prototype.
- For Wailuku, use only the current routes listed above or a current route supplied in CURRENT ROUTE CATALOG.
- Never reuse obsolete Wailuku routes such as /branch/wailuku/operations, /services, /management, or their old anchors.
- If uncertain about an exact destination, use the Wailuku section route rather than inventing an anchor.
- The server validates navigation actions, so an invalid navigation action will be discarded.

SITE INTERACTION
When useful, place safe UI actions at the very end of your response using exact blocks such as:
[[ACTION:{"type":"navigate","label":"Open Wailuku Branch Management","url":"/branch/wailuku/branch-management"}]]
[[ACTION:{"type":"open_feedback","label":"Open feedback"}]]
[[ACTION:{"type":"enter_edit_mode","label":"Enter Edit Mode"}]]
[[ACTION:{"type":"open_my_workspace","label":"Open My Workspace"}]]
[[ACTION:{"type":"focus_search","label":"Search workspace"}]]
Do not explain this syntax to the user. Do not invent destructive, privileged, or external-system actions.

CONVERSATION
- Use conversation history so follow-ups make sense.
- Be capable of ordinary conversation, not just navigation.
- When asked where something belongs, explain the hierarchy clearly and provide a navigation action only when you know the current valid route.
"""

def atlas_workspace_context(current_path):
    path = (current_path or "/").split("#",1)[0].split("?",1)[0]
    context = {"path": path, "branch": None, "section": None}
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "branch":
        b = get_branch(parts[1])
        if b:
            context["branch"] = b["name"]
    if len(parts) >= 3 and parts[0] == "branch":
        s = get_section(parts[2], parts[1])
        if s:
            context["section"] = s["name"]
    return context

def atlas_navigation_is_valid(url):
    """Allow Atlas to navigate only to routes represented by the current application index."""
    if not isinstance(url, str) or not url.startswith("/") or url.startswith("//"):
        return False
    base = url.split("#", 1)[0].split("?", 1)[0]
    if base in {"/", "/prototype", "/authentication"}:
        return True
    # SEARCH_INDEX is built from the same branch/section definitions used by Flask routes.
    return any((item.get("url") or "").split("#", 1)[0] == base for item in globals().get("SEARCH_INDEX", []))

def parse_atlas_actions(text):
    actions = []
    pattern = re.compile(r'\[\[ACTION:(\{.*?\})\]\]')
    for raw in pattern.findall(text or ""):
        try:
            action = json.loads(raw)
            if action.get("type") in {"navigate", "open_feedback", "enter_edit_mode", "open_my_workspace", "focus_search"}:
                if action.get("type") != "navigate" or atlas_navigation_is_valid(action.get("url")):
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

# Wailuku uses its finalized branch-specific OneDrive information architecture.
# Other branches continue to use the original countywide four-area prototype structure.
WAILUKU_SECTIONS=[
 {'slug':'staff','name':'Staff','description':'Staff information, scheduling, onboarding, training, meetings, performance, and student helper or volunteer support.','items':[
   {'slug':'staff-information','name':'Staff Information','children':[{'slug':'directory-contacts','name':'Directory & Contacts'},{'slug':'roles-responsibilities','name':'Roles & Responsibilities'}]},
   {'slug':'scheduling-coverage','name':'Scheduling & Coverage','children':[{'slug':'staff-schedules','name':'Staff Schedules'},{'slug':'leave-absences','name':'Leave & Absences'},{'slug':'coverage','name':'Coverage'}]},
   {'slug':'onboarding-offboarding','name':'Onboarding & Offboarding'}, {'slug':'training-professional-development','name':'Training & Professional Development'},
   {'slug':'staff-meetings','name':'Staff Meetings','children':[{'slug':'agendas','name':'Agendas'},{'slug':'minutes-notes','name':'Minutes & Notes'}]},
   {'slug':'performance-development','name':'Performance & Development'}, {'slug':'student-helpers-volunteers','name':'Student Helpers & Volunteers'}]},
 {'slug':'patron-services','name':'Patron Services','description':'Circulation, accounts, requests, reference, digital services, public technology, accessibility, and public-space use.','items':[
   {'slug':'circulation','name':'Circulation','children':[{'slug':'checkouts-returns-renewals','name':'Checkout, Return & Renewal'},{'slug':'holds','name':'Holds'},{'slug':'lost-damaged-items','name':'Lost & Damaged Items'},{'slug':'fines-fees','name':'Fines & Fees'}]},
   {'slug':'patron-accounts','name':'Patron Accounts'},{'slug':'requests-interlibrary-services','name':'Requests & Interlibrary Services'},{'slug':'reference-information','name':'Reference & Information'},{'slug':'digital-library-services','name':'Digital Library Services'},{'slug':'public-computers-internet','name':'Public Computers & Internet'},{'slug':'printing-copying-scanning','name':'Printing, Copying & Scanning'},{'slug':'accessibility-services','name':'Accessibility Services'},{'slug':'public-spaces-room-use','name':'Public Spaces & Room Use'}]},
 {'slug':'collections','name':'Collections','description':'Collection development and ordering, receiving and processing, maintenance, inventory, and donations for Wailuku and Bookmobile collections.','items':[
   {'slug':'collection-development-ordering','name':'Collection Development & Ordering','resource_name':'Order Lists','children':[{'slug':'wailuku-orders','name':'Wailuku','children':[{'slug':'adult-orders','name':'Adult'},{'slug':'young-adult-orders','name':'Young Adult'},{'slug':'juvenile-orders','name':'Juvenile'},{'slug':'audiovisual-other-orders','name':'Audiovisual & Other Formats'}]},{'slug':'bookmobile-orders','name':'Bookmobile','children':[{'slug':'bookmobile-adult-orders','name':'Adult'},{'slug':'bookmobile-young-adult-orders','name':'Young Adult'},{'slug':'bookmobile-juvenile-orders','name':'Juvenile'},{'slug':'bookmobile-audiovisual-other-orders','name':'Audiovisual & Other Formats'}]}]},
   {'slug':'receiving-processing','name':'Receiving & Processing','children':[{'slug':'wailuku-receiving','name':'Wailuku'},{'slug':'bookmobile-receiving','name':'Bookmobile'}]},
   {'slug':'collection-maintenance','name':'Collection Maintenance','children':[{'slug':'inventory','name':'Inventory'},{'slug':'weeding-withdrawal','name':'Weeding & Withdrawal'},{'slug':'repair-replacement','name':'Repair & Replacement'},{'slug':'shelf-maintenance','name':'Shelf Maintenance'}]},
   {'slug':'donations','name':'Donations','resource_name':'Donations & Honorbacks'}]},
 {'slug':'programs-outreach','name':'Programs & Outreach','description':'Programs by audience, outreach activity, branch-wide program planning, displays, and exhibits.','items':[
   {'slug':'childrens-programs','name':"Children's Programs"},{'slug':'teen-programs','name':'Teen Programs'},{'slug':'adult-programs','name':'Adult Programs'},{'slug':'family-all-ages-programs','name':'Family & All-Ages Programs'},
   {'slug':'outreach','name':'Outreach','children':[{'slug':'schools','name':'Schools'},{'slug':'community-organizations','name':'Community Organizations'},{'slug':'community-events','name':'Community Events'},{'slug':'outreach-planning','name':'Outreach Planning','resource_name':'Planning Resources'}]},
   {'slug':'program-planning','name':'Program Planning'},{'slug':'displays-exhibits','name':'Displays & Exhibits'}]},
 {'slug':'bookmobile','name':'Bookmobile','description':'Bookmobile-specific service schedules, stops, vehicle records, inspections, maintenance, fuel, and mileage.','items':[
   {'slug':'service-schedule-stops','name':'Service Schedule & Stops'},
   {'slug':'vehicle-operations','name':'Vehicle Operations','children':[{'slug':'vehicle-records','name':'Vehicle Records'},{'slug':'inspections-readiness','name':'Inspections & Readiness','resource_path':['Vehicle Operations','Vehicle Records','Inspections']},{'slug':'maintenance-repairs','name':'Maintenance & Repairs','resource_path':['Vehicle Operations','Vehicle Records','Maintenance & Repairs']},{'slug':'fuel-mileage','name':'Fuel & Mileage','resource_path':['Vehicle Operations','Vehicle Records','Fuel & Mileage']}]}]},
 {'slug':'facilities','name':'Facilities','description':'Building information, maintenance and repairs, janitorial operations, grounds, furniture and equipment, access, and inspections.','items':[
   {'slug':'building-information-spaces','name':'Building Information & Spaces','children':[{'slug':'building-information','name':'Building Information'},{'slug':'floor-plans','name':'Floor Plans','resource_name':'Floor Plans & Layout'},{'slug':'space-information','name':'Space Information'}]},
   {'slug':'maintenance-repairs','name':'Maintenance & Repairs','children':[{'slug':'maintenance-requests','name':'Maintenance Requests'},{'slug':'service-repair-records','name':'Service & Repair Records'}]},
   {'slug':'janitorial','name':'Janitorial','children':[{'slug':'cleaning-schedules','name':'Cleaning Schedules','resource_name':'Cleaning Schedule & Procedures'},{'slug':'cleaning-procedures','name':'Cleaning Procedures','resource_name':'Cleaning Schedule & Procedures'},{'slug':'janitorial-equipment','name':'Janitorial Equipment','resource_name':'Janitorial Equipment & Supplies'}]},
   {'slug':'grounds-exterior','name':'Grounds & Exterior'},{'slug':'furniture-equipment','name':'Furniture & Equipment'},{'slug':'keys-building-access','name':'Keys & Building Access','resource_path':['Building Information & Spaces','Keys & Building Access']},{'slug':'facility-inspections','name':'Facility Inspections'}]},
 {'slug':'technology','name':'Technology','description':'Branch computers and devices, printing equipment, network, phones, audiovisual equipment, systems, inventory, and technical support.','items':[
   {'slug':'computers-devices','name':'Computers & Devices','children':[{'slug':'staff-devices','name':'Staff'},{'slug':'public-devices','name':'Public'}]}, {'slug':'printers-copiers-scanners','name':'Printers, Copiers & Scanners','resource_name':'Printers, Copiers, Scanners'},{'slug':'network-wifi','name':'Network & Wi-Fi','resource_name':'Network & Wifi'},{'slug':'phones','name':'Phones'},{'slug':'audiovisual-equipment','name':'Audiovisual Equipment'},{'slug':'library-systems-software','name':'Library Systems & Software'},{'slug':'technology-inventory','name':'Technology Inventory'},{'slug':'technology-support','name':'Technology Support','resource_name':'Tech Support'}]},
 {'slug':'safety-security','name':'Safety & Security','description':'Emergency preparedness, security procedures, patron behavior, incident reporting, workplace safety, and emergency equipment.','items':[
   {'slug':'emergency-preparedness','name':'Emergency Preparedness','children':[{'slug':'emergency-contacts','name':'Emergency Contacts'},{'slug':'emergency-procedures','name':'Emergency Procedures','children':[{'slug':'evacuation','name':'Evacuation'},{'slug':'disaster-response','name':'Disaster Response'}]}]},
   {'slug':'security-procedures','name':'Security Procedures','resource_path':['Emergency Preparedness','Security Procedures']},
   {'slug':'patron-behavior','name':'Patron Behavior','resource_path':['Emergency Preparedness','Patron Behavior']},
   {'slug':'incident-reports','name':'Incident Reports','resource_path':['Emergency Preparedness','Patron Behavior','Incident Reports']},
   {'slug':'workplace-safety','name':'Workplace Safety','resource_path':['Emergency Preparedness','Workplace Safety']},
   {'slug':'safety-emergency-equipment','name':'Safety & Emergency Equipment','resource_path':['Emergency Preparedness','Workplace Safety','Safety & Emergency Equipment']}]},
 {'slug':'finance-purchasing','name':'Finance & Purchasing','description':'Budget planning, expenditure tracking, purchasing, cash and deposits, and financial reporting.','items':[
   {'slug':'budget','name':'Budget','children':[{'slug':'budget-planning','name':'Budget Planning'},{'slug':'expenditure-tracking','name':'Expenditure Tracking'}]},
   {'slug':'purchasing','name':'Purchasing','children':[{'slug':'supply-lists','name':'Supply Lists','resource_name':'Purchase Orders & Supply Lists'},{'slug':'purchase-requests','name':'Purchase Requests'},{'slug':'purchase-orders','name':'Purchase Orders','resource_name':'Purchase Orders & Supply Lists'},{'slug':'invoices-receipts','name':'Invoices & Receipts','resource_path':['Purchase Orders & Supply Lists','Invoices & Receipts']}]},
   {'slug':'cash-deposits','name':'Cash & Deposits'},{'slug':'financial-reports','name':'Financial Reports','resource_path':['Budget','Budget Planning','Financial Reports']}]},
 {'slug':'branch-management','name':'Branch Management','description':'Daily branch operations, deadlines, goals and planning, statistics, policies, correspondence, records management, assessments, and surveys.','items':[
   {'slug':'daily-branch-operations','name':'Daily Branch Operations','resource_name':'Daily Operations','children':[{'slug':'opening','name':'Opening'},{'slug':'closing','name':'Closing'}]}, {'slug':'branch-calendar-deadlines','name':'Branch Calendar & Deadlines'},
   {'slug':'goals-planning','name':'Goals & Planning','children':[{'slug':'branch-goals','name':'Branch Goals'},{'slug':'strategic-planning','name':'Strategic Planning'},{'slug':'service-planning','name':'Service Planning'}]},
   {'slug':'branch-statistics-reports','name':'Branch Statistics & Reports','children':[{'slug':'monthly-statistics','name':'Monthly Statistics'},{'slug':'annual-statistics','name':'Annual Statistics'},{'slug':'branch-reports','name':'Branch Reports'}]},
   {'slug':'policies','name':'Policies'},{'slug':'official-correspondence','name':'Official Correspondence'},{'slug':'records-management','name':'Records Management'},{'slug':'assessments-surveys','name':'Assessments & Surveys'}]},
 {'slug':'communications','name':'Communications','description':'Newsletters, flyers and posters, website materials, public announcements, media and publicity, branding, photos, and media.','items':[
   {'slug':'newsletters','name':'Newsletters'},{'slug':'flyers-posters','name':'Flyers & Posters'},{'slug':'website','name':'Website'},{'slug':'public-announcements','name':'Public Announcements'},{'slug':'media-publicity','name':'Media & Publicity'},{'slug':'branding-logos','name':'Branding & Logos'},{'slug':'photos-media','name':'Photos & Media','resource_name':'Photos & Videos'}]},
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
def get_section(slug, branch_slug=None):
 sections = WAILUKU_SECTIONS if branch_slug == 'wailuku' else SECTIONS
 return next((s for s in sections if s['slug']==slug),None)

WAILUKU_FILES_ROOT = BASE_DIR / 'static' / 'wailuku-files'

def build_wailuku_file_tree(section_name):
 """Return the packaged Wailuku resource files for one branch section."""
 section_root = WAILUKU_FILES_ROOT / section_name
 if not section_root.exists() or not section_root.is_dir():
  return []

 def walk(folder):
  entries=[]
  for child in sorted(folder.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
   if child.is_dir():
    descendants=walk(child)
    # OneDrive contains many intentional empty placeholders (months, pay periods, etc.).
    # They belong in the source-of-truth architecture, but should not become visible
    # website content until an actual resource exists inside them.
    if descendants:
     entries.append({'type':'folder','name':child.name,'children':descendants})
   elif child.is_file():
    rel=child.relative_to(BASE_DIR/'static').as_posix()
    entry={'type':'file','name':child.name,'path':rel,'ext':child.suffix.lower().lstrip('.') or 'file'}
    if child.suffix.lower() == '.url':
     try:
      for line in child.read_text(errors='ignore').splitlines():
       if line.upper().startswith('URL='):
        entry['external_url']=line.split('=',1)[1].strip()
        entry['ext']='LINK'
        entry['name']=child.stem
        break
     except OSError:
      pass
    entries.append(entry)
  return entries
 return walk(section_root)

def _resource_folder(entries, name):
 return next((r for r in entries if r.get('type') == 'folder' and r.get('name') == name), None)

def _resource_path(entries, path):
 current_entries = entries
 folder = None
 for part in path:
  folder = _resource_folder(current_entries, part)
  if not folder:
   return None
  current_entries = folder.get('children', [])
 return folder

def merge_wailuku_resources(items, resources, root_resources=None):
 """Attach authoritative Wailuku files to their functional UI nodes without duplicating empty OneDrive scaffolding."""
 root_resources = resources if root_resources is None else root_resources
 loose_files=[r for r in resources if r['type']=='file']
 merged=[]
 for item in items:
  node=dict(item)
  if item.get('resource_path'):
   folder=_resource_path(root_resources, item['resource_path'])
  else:
   folder=_resource_folder(resources, item.get('resource_name', item['name']))
  folder_entries=folder.get('children',[]) if folder else []
  child_items=item.get('children',[])
  if child_items:
   node['children']=merge_wailuku_resources(child_items, folder_entries, root_resources)
  node['files']=[r for r in folder_entries if r['type']=='file']
  # Deeper folders are shown only when they contain real resources and are not already
  # represented by an explicit functional child in the interface.
  represented={c.get('resource_name', c['name']) for c in child_items if not c.get('resource_path')}
  node['resource_folders']=[r for r in folder_entries if r['type']=='folder' and r['name'] not in represented]
  merged.append(node)
 # Section-level files are rare; keep them visible rather than silently dropping them.
 if loose_files and merged:
  merged[0].setdefault('files',[]).extend(loose_files)
 return merged

def visible_wailuku_items(items):
 """Keep only UI nodes that lead to an actual resource; preserve OneDrive scaffolding in data, not on screen."""
 visible=[]
 for item in items:
  node=dict(item)
  children=visible_wailuku_items(node.get('children',[]))
  if children:
   node['children']=children
  else:
   node['children']=[]
  if node.get('files') or node.get('resource_folders') or children:
   visible.append(node)
 return visible

def flatten_nodes():
 nodes=[]
 for b in BRANCHES:
  branch_sections = WAILUKU_SECTIONS if b['slug']=='wailuku' else SECTIONS
  nodes.append({'label':b['name'],'url':f"/branch/{b['slug']}",'keywords':f"{b['name']} branch library {b['island']}"})
  for s in branch_sections:
   nodes.append({'label':f"{b['name']} — {s['name']}",'url':f"/branch/{b['slug']}/{s['slug']}",'keywords':f"{b['name']} {s['name']} {s['description']}"})
   def walk(items,trail):
    for item in items:
     label=' › '.join(trail+[item['name']])
     nodes.append({'label':f"{b['name']} — {label}",'url':f"/branch/{b['slug']}/{s['slug']}#{item['slug']}",'keywords':f"{b['name']} {label}"})
     walk(item.get('children',[]),trail+[item['name']])
   walk(s['items'],[s['name']])
   if b['slug'] == 'wailuku':
    def index_resources(entries, trail):
     for entry in entries:
      if entry['type'] == 'folder':
       index_resources(entry.get('children', []), trail + [entry['name']])
      else:
       label=' › '.join(trail + [entry['name']])
       nodes.append({'label':f"{b['name']} — {label}",'url':f"/branch/{b['slug']}/{s['slug']}",'keywords':f"{b['name']} {label} file document resource"})
    index_resources(build_wailuku_file_tree(s['name']), [s['name']])
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
 branch_sections = WAILUKU_SECTIONS if branch_slug == 'wailuku' else SECTIONS
 return render_template('branch.html',branch=b,branch_sections=branch_sections)
@app.get('/branch/<branch_slug>/<section_slug>')
def section(branch_slug,section_slug):
 b,s=get_branch(branch_slug),get_section(section_slug, branch_slug)
 if not b or not s: abort(404)
 if branch_slug == 'wailuku':
  resources = build_wailuku_file_tree(s['name'])
  s = dict(s)
  s['items'] = merge_wailuku_resources(s['items'], resources)
  s['visible_items'] = visible_wailuku_items(s['items'])
 return render_template('section.html',branch=b,section=s)
@app.get('/api/search')
def search():
 q=(request.args.get('q') or '').strip().lower()
 branch=(request.args.get('branch') or '').strip().lower()
 terms=[t for t in q.split() if t]
 scored=[]
 for item in SEARCH_INDEX:
  if branch and f"/branch/{branch}" not in item['url']:
   continue
  hay=(item['label']+' '+item['keywords']).lower()
  if not terms:
   score=1
  else:
   score=sum(4 if t in item['label'].lower() else 1 for t in terms if t in hay)
  if score:
   out=dict(item)
   parts=[p for p in item['url'].split('/') if p]
   out['kind']='branch' if len(parts)==2 else ('section' if len(parts)==3 and '#' not in item['url'] else 'area')
   out['branch_slug']=parts[1] if len(parts)>=2 and parts[0]=='branch' else ''
   scored.append((score,out))
 scored.sort(key=lambda x:(-x[0],x[1]['label']))
 return jsonify([i for _,i in scored[:20]])
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
    if page_context["branch"] == "Wailuku Public Library" or current_path.startswith("/branch/wailuku"):
        route_items = [i for i in SEARCH_INDEX if i.get("url", "").startswith("/branch/wailuku")]
    else:
        route_items = [i for i in SEARCH_INDEX if i.get("url", "").count("/") <= 3]
    route_catalog = "\n".join(f"- {i['label']}: {i['url']}" for i in route_items[:120])
    context_text = (
        "\n\nCURRENT WORKSPACE CONTEXT\n"
        f"- Current path: {page_context['path']}\n"
        f"- Current branch: {page_context['branch'] or 'Countywide / none'}\n"
        f"- Current section: {page_context['section'] or 'None'}\n"
        "\nCURRENT ROUTE CATALOG (authoritative; do not invent routes)\n"
        f"{route_catalog}\n"
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


@app.get('/manifest.webmanifest')
def manifest():
    payload = {
        "name":"Maui County Library Workspace Prototype",
        "short_name":"Maui Workspace",
        "start_url":"/",
        "scope":"/",
        "display":"standalone",
        "background_color":"#f7f4ef",
        "theme_color":"#173f50",
        "description":"Public prototype for a shared Maui County library staff workspace.",
        "icons":[{"src":"/static/favicon.svg","sizes":"any","type":"image/svg+xml","purpose":"any maskable"}]
    }
    return Response(json.dumps(payload), mimetype='application/manifest+json')

@app.get('/service-worker.js')
def service_worker():
    js = '''const CACHE="mclw-master-v2-wailuku";const CORE=["/","/prototype","/offline","/static/css/app.css","/static/js/app.js","/static/favicon.svg","/static/assets/master-mark.svg","/static/assets/branch-fallback.svg"];self.addEventListener("install",e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting())));self.addEventListener("activate",e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));self.addEventListener("fetch",e=>{if(e.request.method!=="GET")return;e.respondWith(fetch(e.request).then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(e.request,copy));return r}).catch(()=>caches.match(e.request).then(r=>r||caches.match("/offline"))))});'''
    return Response(js, mimetype='application/javascript', headers={'Service-Worker-Allowed':'/'})

@app.get('/offline')
def offline():
    return render_template('offline.html')

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', code=404, title='Page not found', message='That workspace location does not exist in this prototype.'), 404

@app.errorhandler(500)
def server_error(error):
    return render_template('error.html', code=500, title='Something went wrong', message='The prototype hit an unexpected error. Return to the Staff Hub and try again.'), 500

if __name__=='__main__': app.run(debug=os.environ.get('FLASK_DEBUG')=='1')

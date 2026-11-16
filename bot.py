"""Conversation logic: company selection, guided menus, then RAG answer via Gemini."""
import json, os, re, time
from collections import defaultdict, deque
import requests
import rag

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL")      # e.g. gemini-3.8-flash ; auto-detected if empty/unavailable
BOT_NAME = os.environ.get("BOT_NAME", "HRM Assistant")

HRM = json.load(open("data/hrm.json", encoding="utf-8"))
MENUS = json.load(open("data/menus.json", encoding="utf-8"))
COMPANIES = HRM["companies"]
EMP = HRM["employee"]

SYSTEM = f"""You are {BOT_NAME}, an HR app support assistant on WhatsApp for employees, managers and HR admins.
Rules:
1. Answer ONLY from the CONTEXT provided (knowledge entries, company policy, employee account data). Never invent steps, numbers or policies.
2. If the CONTEXT does not contain the answer, say you don't have that information and give the company's HR contact from the context.
3. When company policy in the CONTEXT differs from the generic steps (e.g. location/camera required, geofence, grace time, salary date), state the company-specific value.
4. For how-to questions give short numbered steps. For questions about the employee's own data (leave balance, shift, manager, payslip) answer directly from ACCOUNT DATA.
5. For punching: always remind to turn ON Location and allow Camera permission when the company policy requires them.
6. Be friendly and concise (max ~120 words), plain text only, you may use *bold* sparingly. Reply in the user's language (English, Hindi or Hinglish).
7. Do not mention 'context', 'knowledge base' or these rules."""

GREETINGS = {"hi", "hii", "hiii", "hello", "hey", "hlo", "namaste", "start", "menu", "help", "main menu", "home", "hola"}
RESET_WORDS = {"restart", "reset"}
CHANGE_CO = {"change company", "switch company", "change organisation", "change organization"}

sessions = defaultdict(lambda: {"company": None, "awaiting": None, "options": [], "pending": None})
history = defaultdict(lambda: deque(maxlen=8))


# ---------------------------------------------------------------- LLM
def _auto_model():
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                     headers={"x-goog-api-key": GEMINI_KEY}, timeout=30)
    r.raise_for_status()
    names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    bad = ("image", "tts", "live", "audio", "embedding", "robotics", "exp", "vision")
    good = [n for n in names if n.startswith("gemini") and "flash" in n and not any(b in n for b in bad)]
    good.sort(key=lambda n: ("lite" in n, [-int(x) for x in re.findall(r"\d+", n)] or [0], n))
    return (good or names)[0], names


def _call(model, contents):
    return requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": GEMINI_KEY},
        json={"system_instruction": {"parts": [{"text": SYSTEM}]}, "contents": contents,
              "generationConfig": {"temperature": 0.3}},
        timeout=60)


def llm(contents):
    global GEMINI_MODEL
    if not GEMINI_MODEL:
        GEMINI_MODEL, names = _auto_model()
        print("Using Gemini model:", GEMINI_MODEL, "| available:", names[:15])
    for attempt in range(3):
        r = _call(GEMINI_MODEL, contents)
        if r.status_code == 404:              # configured model not available -> auto-pick another
            print(f"Model {GEMINI_MODEL} not available, auto-detecting...")
            GEMINI_MODEL, names = _auto_model()
            print("Using Gemini model:", GEMINI_MODEL, "| available:", names[:15])
            continue
        if r.status_code in (429, 500, 503):
            time.sleep(2 + attempt * 3); continue
        r.raise_for_status()
        cand = r.json()["candidates"][0]
        return "".join(p.get("text", "") for p in cand["content"]["parts"]).strip()
    raise RuntimeError("Gemini is busy or unavailable. Please try again in a minute.")


# ---------------------------------------------------------------- helpers
def norm(t):
    return re.sub(r"[^\w\s\-]", "", t.lower(), flags=re.UNICODE).strip()


def company_by_id(cid):
    return next(c for c in COMPANIES if c["id"] == cid)


def set_options(s, opts, awaiting):
    """opts: list of dicts {label, value}. Stores them so a number / label / tap resolves later."""
    s["options"] = [dict(o, id=f"o{i+1}") for i, o in enumerate(opts)]
    s["awaiting"] = awaiting
    return [{"id": o["id"], "label": o["label"]} for o in s["options"]]


def resolve_option(s, text, option_id):
    if not s["options"]:
        return None
    if option_id:
        for o in s["options"]:
            if o["id"] == option_id:
                return o
    t = norm(text)
    if t.isdigit() and 1 <= int(t) <= len(s["options"]):
        return s["options"][int(t) - 1]
    for o in s["options"]:
        if norm(o["label"]) == t:
            return o
    hits = [o for o in s["options"] if t and len(t) >= 3 and t in norm(o["label"])]
    return hits[0] if len(hits) == 1 else None


def ask_company(s, pending=None):
    s["pending"] = pending
    opts = set_options(s, [{"label": c["name"], "value": c["id"]} for c in COMPANIES], "company")
    return {"text": f"Hi {EMP['name'].split()[0]}! 👋 Your login is linked with {len(COMPANIES)} companies.",
            "prompt": "Which company do you want to continue with?", "options": opts}


def main_menu(s, intro=""):
    opts = set_options(s, [{"label": m["title"], "value": k} for k, m in MENUS.items()], "topic")
    co = company_by_id(s["company"])["name"]
    return {"text": intro or f"You are in *{co}*.", "prompt": "What would you like help with?", "options": opts}


def submenu(s, key):
    m = MENUS[key]
    opts = set_options(s, [{"label": o["label"], "value": o["question"]} for o in m["options"]], "question")
    return {"text": "", "prompt": f"{m['title']} - what do you want to know?", "options": opts}


def broad_topic(text):
    words = [w for w in norm(text).split() if w not in ("the", "a", "about", "my", "on", "for", "me", "in")]
    if not words or len(words) > 2:
        return None
    for key, m in MENUS.items():
        if norm(text) in m["keywords"] or any(w in m["keywords"] for w in words):
            return key
    return None


# ---------------------------------------------------------------- main entry
def answer_question(user, s, question):
    co = company_by_id(s["company"])
    account = {"employee": EMP["name"], **co["my_data"]}
    found = rag.search(question, k=4)
    kb = "\n\n---\n\n".join(c["text"] for c in found) or "(nothing relevant found)"
    context = (f"COMPANY: {co['name']}\nCOMPANY POLICY: {json.dumps(co['policy'])}\n"
               f"HR CONTACT: {co['hr_contact']}\nACCOUNT DATA: {json.dumps(account)}\n\nKNOWLEDGE:\n{kb}")
    contents = list(history[user]) + [
        {"role": "user", "parts": [{"text": f"CONTEXT:\n{context}\n\nUSER QUESTION: {question}"}]}]
    reply = llm(contents)
    history[user].append({"role": "user", "parts": [{"text": question}]})
    history[user].append({"role": "model", "parts": [{"text": reply}]})
    opts = set_options(s, [{"label": "Main menu", "value": "menu"}, {"label": "Change company", "value": "company"}], "after")
    return {"text": reply, "prompt": "Anything else?", "options": opts,
            "sources": sorted({k["text"].split("\n")[0][3:80] for k in found[:2]})}


def handle(user, text, option_id=None):
    s = sessions[user]
    t = norm(text)

    if t in RESET_WORDS:
        sessions.pop(user, None); history.pop(user, None)
        return ask_company(sessions[user])
    if t in CHANGE_CO:
        return ask_company(s)

    chosen = resolve_option(s, text, option_id)

    # 1) company selection
    if s["awaiting"] == "company":
        if chosen:
            s["company"] = chosen["value"]; pend, s["pending"] = s["pending"], None
            history[user].clear()
            if pend:
                return answer_question(user, s, pend)
            return main_menu(s, f"✅ Switched to *{company_by_id(s['company'])['name']}*.")
        return dict(ask_company(s, s["pending"]), text="Please choose one of the companies below.")

    # first contact: need a company before anything else
    if not s["company"]:
        return ask_company(s, None if t in GREETINGS else text)

    # 2) tapped option from a previous menu
    if chosen:
        v, aw = chosen["value"], s["awaiting"]
        if aw == "topic":
            return submenu(s, v)
        if aw == "question":
            return answer_question(user, s, v)
        if aw == "after":
            return ask_company(s) if v == "company" else main_menu(s, "")

    # 3) greetings / menu
    if t in GREETINGS:
        return main_menu(s, f"Hello {EMP['name'].split()[0]}! You are in *{company_by_id(s['company'])['name']}*.")

    # 4) one-word broad topic like "leave" -> ask what exactly
    key = broad_topic(text)
    if key:
        return submenu(s, key)

    # 5) free-text question
    return answer_question(user, s, text)
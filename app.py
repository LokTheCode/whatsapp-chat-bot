import os
from dotenv import load_dotenv
load_dotenv()
import requests
from collections import deque
from flask import Flask, request, jsonify, render_template_string
import rag
import bot

app = Flask(__name__)
VERIFY_TOKEN = os.environ["VERIFY_TOKEN"]
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "")
seen = deque(maxlen=500)
GRAPH = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"


def wa_post(payload):
    r = requests.post(GRAPH, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
                      json={"messaging_product": "whatsapp", **payload}, timeout=15)
    if r.status_code >= 400:
        print("WhatsApp send error:", r.status_code, r.text)


def send_result(to, res):
    """Send text, then options as a WhatsApp list (or reply buttons when 3 or fewer)."""
    if res.get("text"):
        wa_post({"to": to, "type": "text", "text": {"body": res["text"][:4000]}})
    opts = res.get("options") or []
    if not opts:
        return
    body = (res.get("prompt") or "Choose an option")[:1000]
    if len(opts) <= 3:
        wa_post({"to": to, "type": "interactive", "interactive": {
            "type": "button", "body": {"text": body},
            "action": {"buttons": [{"type": "reply", "reply": {"id": o["id"], "title": o["label"][:20]}} for o in opts]}}})
    else:
        wa_post({"to": to, "type": "interactive", "interactive": {
            "type": "list", "body": {"text": body},
            "action": {"button": "Choose", "sections": [{"title": "Options", "rows": [
                {"id": o["id"], "title": o["label"][:24]} for o in opts[:10]]}]}}})


CHAT_HTML = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HRM Bot Tester</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Segoe UI,Arial,sans-serif;background:#d1d7db;display:flex;justify-content:center;height:100vh}
#app{width:100%;max-width:480px;display:flex;flex-direction:column;background:#efeae2}
header{background:#008069;color:#fff;padding:14px 16px;font-weight:600}header small{display:block;font-weight:400;opacity:.8}
#msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:6px}
.m{max-width:80%;padding:8px 10px;border-radius:8px;white-space:pre-wrap;box-shadow:0 1px 1px rgba(0,0,0,.15);font-size:15px}
.m i{display:block;font-size:11px;color:#667781;margin-top:4px}
.me{align-self:flex-end;background:#d9fdd3}.bot{align-self:flex-start;background:#fff}
.opts{align-self:flex-start;display:flex;flex-direction:column;gap:5px;max-width:80%}
.opts button{background:#fff;color:#008069;border:1px solid #008069;border-radius:18px;padding:8px 12px;font-size:14px;cursor:pointer;text-align:left}
.opts button:hover{background:#e7f6f3}
form{display:flex;gap:8px;padding:10px;background:#f0f2f5}input{flex:1;padding:11px 14px;border:0;border-radius:20px;font-size:15px;outline:none}
form button{background:#008069;color:#fff;border:0;border-radius:50%;width:44px;font-size:18px;cursor:pointer}
</style></head><body><div id="app"><header>HRM Assistant<small id="st">online</small></header>
<div id="msgs"></div><form id="f"><input id="t" placeholder="Type a message (try: hi)" autocomplete="off" autofocus><button>&#10148;</button></form></div>
<script>
const msgs=document.getElementById('msgs'),t=document.getElementById('t'),st=document.getElementById('st');
function add(txt,c,src){if(!txt)return;const d=document.createElement('div');d.className='m '+c;d.textContent=txt;
if(src&&src.length){const i=document.createElement('i');i.textContent='Source: '+src.join(' | ');d.appendChild(i)}
msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight}
function clearOpts(){document.querySelectorAll('.opts').forEach(e=>e.remove())}
async function send(text,id){clearOpts();add(text,'me');st.textContent='typing...';
try{const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,option_id:id})});
const j=await r.json();if(j.error){add(j.error,'bot');}else{add(j.text,'bot',j.sources);add(j.prompt,'bot');
if(j.options&&j.options.length){const w=document.createElement('div');w.className='opts';
j.options.forEach(o=>{const b=document.createElement('button');b.textContent=o.label;b.onclick=()=>send(o.label,o.id);w.appendChild(b)});msgs.appendChild(w)}}}
catch(x){add('Error: '+x,'bot')}st.textContent='online';msgs.scrollTop=msgs.scrollHeight}
document.getElementById('f').onsubmit=e=>{e.preventDefault();const v=t.value.trim();if(!v)return;t.value='';send(v,null)};
</script></body></html>"""


@app.get("/")
def home():
    return render_template_string(CHAT_HTML)


@app.post("/chat")
def chat():
    d = request.get_json(silent=True) or {}
    text = (d.get("message") or "").strip()
    if not text:
        return jsonify(error="empty message"), 400
    try:
        return jsonify(bot.handle("local-test-user", text, d.get("option_id")))
    except Exception as e:
        app.logger.exception(e)
        return jsonify(error=f"Error: {e}"), 500


@app.get("/reload")
def reload_kb():
    return jsonify(chunks=rag.load())


@app.get("/webhook")
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge", ""), 200
    return "forbidden", 403


@app.post("/webhook")
def incoming():
    data = request.get_json(silent=True) or {}
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                for msg in change["value"].get("messages", []):
                    if msg["id"] in seen:
                        continue
                    seen.append(msg["id"])
                    sender, mtype = msg["from"], msg.get("type")
                    if mtype == "text":
                        text, oid = msg["text"]["body"], None
                    elif mtype == "interactive":
                        rep = msg["interactive"].get("list_reply") or msg["interactive"].get("button_reply")
                        text, oid = rep["title"], rep["id"]
                    else:
                        wa_post({"to": sender, "type": "text", "text": {"body": "Sorry, I can only read text messages for now."}})
                        continue
                    send_result(sender, bot.handle(sender, text, oid))
    except Exception as e:
        app.logger.exception(e)
    return jsonify(ok=True), 200


rag.load()
if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5000)))
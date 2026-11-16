# HRM WhatsApp Assistant

A WhatsApp chatbot that answers HR-app support questions (punching in, leave, payroll, adding employees and more) using **your own knowledge files**, and guides users with selectable options. It works with the Meta WhatsApp Cloud API and Google Gemini, and the whole setup can run on free tiers.

It also includes a local WhatsApp-style test page, so you can try the bot in a browser without WhatsApp.

---

## What it does

- **Answers from your content, not from guesswork.** It searches your files for the most relevant entries and gives them to Gemini, which answers only from that. If the answer isn't in your files, it says so and gives the company's HR contact.
- **Multi-company login.** If a user belongs to several companies, the bot first asks which one to continue with. Answers then use that company's policy (for example, whether location and camera are required to punch).
- **Guided options.** Typing `hi` or `menu` shows a topic menu. Typing a broad word such as `leave` or `salary` asks what exactly the user wants to know. On WhatsApp these appear as tappable lists and buttons.
- **Personal account data.** Questions like "what is my leave balance?" are answered from the user's data (dummy data in this demo).
- **127 ready-made HRM questions and answers** covering the topics below.

| Area | Examples |
|---|---|
| Attendance and punch | punch in/out, enable location and camera, outside-area error, missed punch, late mark |
| Leave | apply, balance, cancel, half-day, comp-off, policy |
| Payroll | payslip, salary date, deductions, tax declaration, Form 16 |
| Employees (HR/Admin) | add, bulk import, edit, deactivate, exit |
| Shifts and holidays | shift change, swap, roster, holiday list |
| Expenses and reports | claims, receipts, attendance/leave/payroll reports |
| Login and support | password reset, OTP, switch company, raise a ticket |

---

## How it works

```
 User message (WhatsApp or test page)
          |
          v
   bot.py: conversation flow
     - no company chosen?  -> ask which company
     - "hi" / "menu"       -> show topic menu
     - one broad word      -> show sub-options
     - a real question     -> continue below
          |
          v
   rag.py: search knowledge/*.md (free keyword search, BM25)
          |
          v
   Gemini: answers using the matching entries + company policy + account data
          |
          v
 Reply (text + option buttons)
```

## Project structure

```
app.py                  Flask server: test page, WhatsApp webhook, sending messages
bot.py                  Conversation logic, company selection, menus, Gemini call
rag.py                  Loads files, splits them into chunks, searches them
data/hrm.json           Dummy employee and 5 dummy companies (policies, leave balances)
data/menus.json         Topic menu and sub-options
knowledge/*.md          The FAQ content the bot answers from
requirements.txt        Python packages
.env                    Your keys (you create this; never share or commit it)
```

---

## Quick start (local test, no WhatsApp needed)

You need Python 3.10+ and a free Gemini API key from <https://aistudio.google.com/apikey>.

```bash
pip install -r requirements.txt
```

Create a file named `.env` in the project folder:

```dotenv
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=
VERIFY_TOKEN=any-secret-word-you-choose
BOT_NAME=HRM Assistant
```

Run it:

```bash
python app.py
```

Open **http://127.0.0.1:5000** (use `http`, not `https`) and type `hi`.

Type `restart` in the chat to start over.

`GEMINI_MODEL` can stay empty. The bot then picks a current Flash model that your key can use and prints its name in the terminal. To force a specific model, put its exact name there.

---

## Connect it to real WhatsApp (free test setup)

1. Create an app at <https://developers.facebook.com> and add the **Connect with customers through WhatsApp** use case.
2. In the left menu open **Basic setup > Step 1. Try it out**. Copy the **Temporary access token** (valid 24 hours) and the **Phone number ID**. Add your own number in the **To** box and verify it with the code Meta sends.
3. Add both values to `.env`:
   ```dotenv
   WHATSAPP_TOKEN=EAAG...
   PHONE_NUMBER_ID=1234567890
   ```
4. Start the app (`python app.py`), then expose it with a free tunnel such as `ngrok http 5000` (or `cloudflared tunnel --url http://localhost:5000`).
5. In **Step 2. Production setup > Configure Webhooks** set:
   - Callback URL: `https://<your-tunnel-address>/webhook`
   - Verify token: the same value as `VERIFY_TOKEN`
   - Turn off "Attach a client certificate", then click **Verify and save**
   - Subscribe to the **messages** field
6. From your phone, send `hi` to the Meta test number.

Notes:
- The Meta test number can only message the recipients you added, and replies inside 24 hours are free.
- You do not need the "Register phone number" or "Add payment" steps for testing.
- The temporary token expires every 24 hours. Generate a new one and update `.env`.

---

## Adding your own content

1. Put files in the `knowledge/` folder. Supported types: `.md`, `.txt`, `.csv`, `.pdf`, `.docx`.
2. For best results write FAQ files in this format. Each pair becomes one searchable entry:
   ```
   Q: How do I punch in?
   A: Open Attendance > tap Punch In. Turn on Location and allow Camera first.
   ```
   Other documents are split automatically into chunks of about 800 characters.
3. Open `http://127.0.0.1:5000/reload` (or restart the app) to load the changes.

Other things to customise:
- **Companies, policies and employee data:** `data/hrm.json`
- **Topic menu and sub-options:** `data/menus.json`
- **Bot name and tone:** `BOT_NAME` in `.env` and the `SYSTEM` prompt in `bot.py`

## Try these in the chat

| You type | The bot does |
|---|---|
| `hi` | Asks which of the 5 companies, then shows the topic menu |
| `punch` | Shows punch sub-options (how to punch in, enable location, enable camera...) |
| `How do I add a new employee?` | Gives the steps from the knowledge base |
| `What is my leave balance?` | Answers from the account data of the chosen company |
| `change company` | Lets you switch company and applies that company's policy |

---

## Limits to know about

- **Demo data:** The companies, the employee and the "login" are dummy data in `data/hrm.json`. A real deployment must identify the user (for example by their WhatsApp number) and load their real companies and data from your HRM system.
- **Memory:** Conversation state is kept in memory and is lost when the app restarts.
- **Search:** Search matches keywords, not meaning, so questions that share words with your content work best. For large or varied content, embedding-based search would be a good upgrade.
- **Free tiers:** Gemini's free tier has rate limits and can be slow at times. The bot retries automatically a few times.
- **Production:** Use a permanent access token (system user), a real hosting service instead of a tunnel, and a production WSGI server such as `gunicorn app:app`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `KeyError: 'VERIFY_TOKEN'` | `.env` is missing, misnamed, or `VERIFY_TOKEN` is not set in it |
| Browser shows garbled "Bad request" lines in the terminal | Open the page with `http://`, not `https://` |
| ngrok error `ERR_NGROK_8012` | The app is not running on port 5000 |
| Webhook "couldn't be validated" | Callback URL must end in `/webhook`, and the verify token must match exactly |
| No reply on WhatsApp | Subscribe to the `messages` field, check the access token has not expired, and look at the terminal for errors |
| Gemini 404 or "model not found" | Leave `GEMINI_MODEL` empty so a working model is auto-selected |
| Gemini timeout or 429 | Free tier is busy or rate limited. Wait a minute and try again |

## Security

Never commit `.env` or share your API keys and tokens. Add `.env` to `.gitignore`.
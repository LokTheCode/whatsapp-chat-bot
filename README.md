# WhatsApp Claude Bot

1. `pip install -r requirements.txt`
2. Copy `.env.example` values into your environment (export them).
3. `python app.py` (port 5000), then expose it: `ngrok http 5000`
4. Meta developer dashboard > your app > WhatsApp > Configuration:
   - Callback URL: `https://<ngrok-host>/webhook`
   - Verify token: same as VERIFY_TOKEN
   - Subscribe to the `messages` field
5. Message your WhatsApp test number. Done.

For production use gunicorn (`gunicorn app:app`) on a real host and a permanent system-user token.
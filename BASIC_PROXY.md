# Basic FastAPI LLM Proxy

This is the first, simplest version of an LLM gateway. It accepts a prompt at `POST /proxy`, sends the exact prompt to OpenAI, and returns the reply. It has **no** logging, PII removal, rate limiting, caching, or authentication—those belong to the full security gateway in `app/`.

## 1. Install packages

From this project folder, run:

```powershell
python -m pip install -r requirements.txt
```

## 2. Set your OpenAI API key

Create an environment variable for the current PowerShell window. Replace the placeholder with your own secret key; never paste it into source code or commit it to Git.

```powershell
$env:OPENAI_API_KEY = "your_api_key_here"
$env:OPENAI_MODEL = "gpt-4.1-mini"
```

## 3. Start the proxy

```powershell
python -m uvicorn basic_proxy:app --reload --port 8001
```

Keep this terminal open. Then visit `http://127.0.0.1:8001/docs` to see and try the API in your browser.

## 4. Send a request

Open a second PowerShell terminal, set the same `OPENAI_API_KEY`, and run:

```powershell
$body = @{ prompt = "Explain phishing in one sentence." } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8001/proxy -Method Post -ContentType "application/json" -Body $body
```

Expected response shape:

```json
{
  "response": "...",
  "model": "gpt-4.1-mini"
}
```

## How it works

```text
Your PowerShell request -> FastAPI /proxy -> OpenAI API -> FastAPI response -> You
```

Once this works, move to the full `app/main.py` gateway. It keeps the same OpenAI forwarding idea, but puts policy checks, audit logging, Redis rate limiting/cache, and the dashboard around it.

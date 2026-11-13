#!/usr/bin/env python3
"""Fan one prompt out to several AI providers in parallel and print every answer.

Stdlib only, no install step. API keys are read from environment variables and are never
printed, logged or echoed. Only the provider name and its answer (or a short error) come back.

Set whichever of these you have. Providers without a key are skipped.
  OPENAI_API_KEY      OpenAI direct
  GEMINI_API_KEY      Google Gemini direct
  XAI_API_KEY         xAI (Grok) direct
  OPENROUTER_API_KEY  reaches any of the three above when its direct key is missing,
                      and any other OpenRouter model through --models

Usage:
  python consult.py < prompt.txt
  python consult.py --dry-run < prompt.txt          # show who would be called, call nobody
  python consult.py --models openai,gemini < prompt.txt
  python consult.py --models openrouter:anthropic/claude-sonnet-4.5,xai < prompt.txt

Every call is billed to your own keys. Run --dry-run first if you are unsure what it will cost.

Exit codes: 0 at least one answer, 1 every provider failed, 2 nothing to call (no keys / bad input).
"""
import argparse, concurrent.futures, io, json, os, sys, urllib.error, urllib.request

# Reasoning models on a long prompt can take several minutes.
TIMEOUT = int(os.environ.get("CONSULT_TIMEOUT", "600"))
# Output cap per provider. Too small and reasoning models spend it all on thinking and return
# nothing; with none at all some routers ask for the model maximum and reject the request.
MAX_OUTPUT = int(os.environ.get("CONSULT_MAX_OUTPUT", "16000"))

# Model ids drift and providers retire them. A 404 or "model not found" almost always means a
# stale id here, not a broken key. Override any of them with the env var in the last column.
PROVIDERS = {
    #  name      key env var        direct model             OpenRouter model                  override env var
    "openai": ("OPENAI_API_KEY", "gpt-5",                  "openai/gpt-5.6-sol",            "CONSULT_OPENAI_MODEL"),
    "gemini": ("GEMINI_API_KEY", "gemini-3.1-pro-preview", "google/gemini-3.1-pro-preview", "CONSULT_GEMINI_MODEL"),
    "xai":    ("XAI_API_KEY",    "grok-4",                 "x-ai/grok-4.7",                 "CONSULT_XAI_MODEL"),
}
KEY_VARS = [p[0] for p in PROVIDERS.values()] + ["OPENROUTER_API_KEY"]

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
XAI_URL = "https://api.x.ai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _post(url, headers, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode())


def call_openai_shaped(url, key, model, prompt):
    """OpenAI, xAI and OpenRouter all accept this request shape."""
    cap = "max_completion_tokens" if "openai.com" in url else "max_tokens"
    d = _post(url, {"Authorization": "Bearer " + key},
              {"model": model, "messages": [{"role": "user", "content": prompt}], cap: MAX_OUTPUT})
    return d["choices"][0]["message"]["content"]


def call_gemini(key, model, prompt):
    """Key goes in a header, not the query string, so it never lands in a logged URL."""
    d = _post(GEMINI_URL % model, {"x-goog-api-key": key},
              {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"maxOutputTokens": MAX_OUTPUT}})
    return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])


def resolve(spec):
    """Turn a spec into (label, route, model, key_var) or (label, None, None, reason).
    route is 'openai' | 'gemini' | 'xai' | 'openrouter'."""
    if spec.startswith("openrouter:"):
        model = spec.split(":", 1)[1]
        if not os.environ.get("OPENROUTER_API_KEY"):
            return spec, None, None, "OPENROUTER_API_KEY not set"
        return spec, "openrouter", model, "OPENROUTER_API_KEY"
    if spec not in PROVIDERS:
        return spec, None, None, "unknown provider (use openai, gemini, xai or openrouter:<model>)"
    key_var, direct_model, or_model, override = PROVIDERS[spec]
    if os.environ.get(key_var):
        return spec, spec, os.environ.get(override, direct_model), key_var
    if os.environ.get("OPENROUTER_API_KEY"):
        return spec + " via OpenRouter", "openrouter", os.environ.get(override, or_model), "OPENROUTER_API_KEY"
    return spec, None, None, "%s not set (and no OPENROUTER_API_KEY)" % key_var


def clean_error(text, key):
    """Collapse whitespace, truncate, and scrub the key in case a provider echoes it back."""
    text = " ".join(str(text).split())[:300]
    return text.replace(key, "[redacted]") if key else text


def call(plan, prompt):
    label, route, model, key_var = plan
    key = os.environ.get(key_var, "")
    try:
        if route == "openai":
            text = call_openai_shaped(OPENAI_URL, key, model, prompt)
        elif route == "xai":
            text = call_openai_shaped(XAI_URL, key, model, prompt)
        elif route == "gemini":
            text = call_gemini(key, model, prompt)
        else:
            text = call_openai_shaped(OPENROUTER_URL, key, model, prompt)
        if not text:
            return label, model, None, "empty answer (raise CONSULT_MAX_OUTPUT if this is a reasoning model)"
        return label, model, text, None
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        hint = {401: "authentication failed, check %s" % key_var,
                403: "access denied, check %s and its permissions" % key_var,
                404: "model not found, the id '%s' may be stale" % model,
                429: "rate limited or out of credit"}.get(e.code, "request failed")
        # Gemini and xAI answer a bad key with 400, not 401.
        if e.code == 400 and "api key" in body.lower():
            hint = "authentication failed, check %s" % key_var
        return label, model, None, "HTTP %s, %s. %s" % (e.code, hint, clean_error(body, key))
    except Exception as e:
        return label, model, None, "%s: %s" % (type(e).__name__, clean_error(e, key))


def main():
    ap = argparse.ArgumentParser(description="Ask several AI providers the same question.")
    ap.add_argument("--models", help="comma-separated: openai, gemini, xai, openrouter:<model id>")
    ap.add_argument("--dry-run", action="store_true", help="show who would be called and the prompt size, call nobody")
    a = ap.parse_args()

    # Windows consoles default to cp1252 and crash on the first arrow or emoji a model returns.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    specs = [s.strip() for s in a.models.split(",") if s.strip()] if a.models else list(PROVIDERS)
    plans = [resolve(s) for s in specs]
    ready = [p for p in plans if p[1]]
    for label, route, _, reason in plans:
        if not route:
            print("skipped %s: %s" % (label, reason), file=sys.stderr)

    if not ready:
        print("\nNo provider to call. Set at least one of these environment variables:\n  "
              + "\n  ".join(KEY_VARS)
              + "\nSee the README for where to get each key.", file=sys.stderr)
        return 2

    if sys.stdin.isatty():
        print("Pipe the prompt in on stdin, e.g.  python consult.py < prompt.txt", file=sys.stderr)
        return 2
    # Read stdin as UTF-8 regardless of console code page, or the APIs reject the JSON.
    prompt = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace").read().strip()
    if not prompt:
        print("No prompt on stdin.", file=sys.stderr)
        return 2

    if a.dry_run:
        # About 4 characters per token for English text. A rough guide, not a bill.
        print("Would call %d provider(s):" % len(ready))
        for label, _, model, key_var in ready:
            print("  %-24s model %-28s key %s" % (label, model, key_var))
        print("Prompt: %d characters, roughly %d input tokens per provider." % (len(prompt), len(prompt) // 4))
        print("Output cap: %d tokens per provider (reasoning tokens usually count as output)." % MAX_OUTPUT)
        print("Cost per provider = input tokens x its input price + output tokens x its output price.")
        print("Check each provider's current pricing page; prices change and are not stored here.")
        return 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ready)) as ex:
        results = list(ex.map(lambda p: call(p, prompt), ready))

    ok = 0
    for label, model, text, err in results:
        print("=" * 70)
        print("%s (%s)" % (label.upper(), model))
        print("=" * 70)
        print(text if text is not None else "FAILED: " + err)
        print()
        ok += text is not None
    print("%d/%d answered" % (ok, len(results)), file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

# consult: a Claude Code skill for getting a second, third and fourth opinion

Some decisions are expensive to get wrong. Which database. Which vendor. Whether to rebuild
or patch. Claude gives you a confident answer, but it is one model with one set of blind
spots and a training cutoff.

`consult` sends the same question to several other AI models at once, on your own API keys,
and has Claude compare the answers: where they agree, where they disagree, and what that
changes about the decision.

## What it does

1. **Knows when not to run.** Claude only offers a consult for decisions that change the
   direction of the work and that outside information could move. Not for doc lookups, not
   for routine choices, not for anything cheap to undo. It asks you first, once per decision.
2. **Writes one standalone prompt.** The other models see nothing of your project, so
   Claude writes a prompt that carries all the context: the decision, the constraints, the
   options, what is already ruled out, and an explicit ask for the strongest case against
   the leading option. It strips names, credentials and internal details first, and shows you
   the prompt before sending.
3. **Fans it out in parallel.** `consult.py` calls every provider you have a key for at the
   same time. Providers without a key are skipped.
4. **Reconciles.** Claude reports what the models agreed on, where they conflicted (and
   which side it believes, and why), what changes the decision, and what is still open. Then
   it makes the call and keeps working.

## Example

You are choosing between two background job systems for an app. Claude says:

> This is a directional call. Want me to consult the other models? It runs on your API keys.

You say yes. It writes the prompt, shows it to you, runs it, and comes back with something
like:

```
Agreed (3/3): the managed queue is the safer default at your volume.
Conflicted: one model says the self-hosted option is cheaper above 1M jobs/month,
  another says ops time erases the saving. The second cites a dated cost breakdown,
  so I'm siding with it.
Changes the decision: two models flag that the managed queue's free tier changed
  this year. I hadn't accounted for that.
Still open: none of them knew the retry limits for long-running jobs. Checking the docs.
Decision: managed queue. Moving on.
```

## Cost

**Every call is billed to your own API keys.** A consult with three providers is three paid
requests. Reasoning models can produce a lot of output, and output is usually the expensive
side.

Estimate before you run a long prompt:

```bash
python ~/.claude/skills/consult/consult.py --dry-run < prompt.txt
```

That calls nobody. It shows which providers and models would be used, the prompt length,
and a rough input token count (about 4 characters per token). Then:

```
cost per provider = input tokens x input price + output tokens x output price
```

Use each provider's current pricing page for the prices. They change, so none are stored
here. Output per provider is capped by `CONSULT_MAX_OUTPUT` (default 16000 tokens), which
also caps the worst case. Most providers let you set a monthly spend limit on the key itself;
that is worth doing.

## Install

You need [Claude Code](https://docs.claude.com/en/docs/claude-code) and Python 3.8 or newer.
No packages to install, the script uses the standard library only.

**1. Copy the skill.**

macOS / Linux:

```bash
git clone https://github.com/milansolutionsai-ops/claude-code-consult.git
mkdir -p ~/.claude/skills
cp -r claude-code-consult/skills/consult ~/.claude/skills/
```

Windows (PowerShell):

```powershell
git clone https://github.com/milansolutionsai-ops/claude-code-consult.git
New-Item -ItemType Directory -Force "$HOME\.claude\skills"
Copy-Item -Recurse claude-code-consult\skills\consult "$HOME\.claude\skills\"
```

**2. Set the keys you have.** Any one is enough. More providers means more independent
opinions.

| Variable | Provider | Get a key |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI | platform.openai.com |
| `GEMINI_API_KEY` | Google Gemini | aistudio.google.com |
| `XAI_API_KEY` | xAI (Grok) | console.x.ai |
| `OPENROUTER_API_KEY` | OpenRouter | openrouter.ai |

With only an OpenRouter key, the script reaches all three through OpenRouter. With a direct
key, the direct one is used for that provider. OpenRouter also reaches models not listed
above:

```bash
python ~/.claude/skills/consult/consult.py --models openrouter:anthropic/claude-sonnet-4.5,openai < prompt.txt
```

Set them the way you normally set environment variables (your shell profile on macOS/Linux,
System Properties > Environment Variables on Windows), then restart Claude Code so it sees
them.

**3. Use it.** Ask Claude for "a second opinion" or to "consult the other models" on a
decision, or let it offer one when it spots a directional call.

## Configuration

| Variable | Default | What it does |
|---|---|---|
| `CONSULT_OPENAI_MODEL` | `gpt-5` direct, `openai/gpt-5.6-sol` via OpenRouter | Model id for OpenAI |
| `CONSULT_GEMINI_MODEL` | `gemini-3.1-pro-preview` | Model id for Gemini |
| `CONSULT_XAI_MODEL` | `grok-4` direct, `x-ai/grok-4.7` via OpenRouter | Model id for xAI |
| `CONSULT_MAX_OUTPUT` | `16000` | Output token cap per provider |
| `CONSULT_TIMEOUT` | `600` | Seconds to wait for each provider |

Model ids change often. If a provider answers "model not found", the id is stale: check that
provider's model list and set the matching variable. If it answers "authentication failed",
the key is wrong or expired.

## Running the script on its own

You can use it without Claude:

```bash
python consult.py < prompt.txt
python consult.py --models openai,gemini < prompt.txt
python consult.py --dry-run < prompt.txt
```

Each answer prints under its own header. Exit code is 0 if at least one provider answered,
1 if all failed, 2 if there was nothing to call (no keys set, or no prompt).

Keys are read from the environment and never printed. Error messages are truncated, and the
key is scrubbed from them in case a provider echoes it back.

## What's in the repo

```
skills/consult/
  SKILL.md      the method: when to consult, how to write the prompt, how to reconcile
  consult.py    the parallel fan-out (Python standard library only)
```

## License

MIT. Use it, change it, ship it.

Built by [Milan Veljkovikj](https://github.com/milansolutionsai-ops).

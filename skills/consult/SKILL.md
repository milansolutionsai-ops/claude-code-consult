---
name: consult
description: Use when a decision would meaningfully change the direction of the work and outside opinions would move it, such as a stack or platform choice, architecture that is expensive to unwind, a vendor, pricing or market call, or anything where current real-world state beats training data. Fans one self-contained prompt out to several AI providers (OpenAI, Gemini, xAI, OpenRouter) on the user's own API keys, then reconciles where they agree and disagree. Triggered by "consult", "ask the other models", "second opinion", "run a research", or by Claude spotting a directional decision. NOT for documentation lookups, routine implementation choices, or anything cheap to reverse.
---

# Consult: fan out, then reconcile

One question, several independent models, one reconciled answer. Claude writes the prompt,
`consult.py` sends it to every provider the user has a key for, and Claude reports where the
answers agree, where they conflict, and what that means for the decision.

**Every call costs money on the user's own API keys.** Treat it like spending their money,
because it is.

## 1. Gate before offering

Offer a consult ONLY when all three hold:

- The decision **changes direction**, not just implementation. Getting it wrong means rework,
  not a quick revert.
- **Outside information or a different model's prior would move it.** Current pricing, live
  platform limits, what the market settled on recently, real-world failure reports, or simply a
  model that does not share your blind spots.
- **Documentation and your own knowledge cannot close it.** Try those first. A library API
  question is never a consult.

Offer it in one line and wait for a yes:

> "This is a directional call. Want me to consult the other models? It runs on your API keys."

Offer once per decision. If the user says no, decide on your own judgment and do not offer
again for that decision. Never fan out during a firefight or mid-debug.

## 2. Setup

The user sets whichever of these environment variables they have. Missing ones are skipped.

| Variable | Provider |
|---|---|
| `OPENAI_API_KEY` | OpenAI |
| `GEMINI_API_KEY` | Google Gemini |
| `XAI_API_KEY` | xAI (Grok) |
| `OPENROUTER_API_KEY` | Fills in any of the three above whose own key is missing, and reaches other models with `--models openrouter:<model id>` |

**Never print, echo, log or paste a key value.** The script reads keys from the environment.
To check one exists, show the variable NAME and its length, never the value.

## 3. Write the prompt

The receiving models have zero context: no repo, no files, no conversation. The prompt must
stand completely alone.

1. **Role and the decision, in one sentence.** What is being chosen, for what.
2. **Context that constrains the answer.** Stack, scale, budget, team size, non-negotiables.
   Real numbers where you have them. Write "unknown" where you don't. Never invent.
3. **The options on the table**, each with why it is a candidate.
4. **What has been ruled out and why**, so the answers do not restate dead ends.
5. **Explicit asks:**
   - A recommendation with reasoning, not a survey.
   - **The strongest case AGAINST the leading option.** The most valuable part; ask for it by name.
   - Anything that changed in the last 12 months that bears on it.
   - Sources with dates, and a flag on anything it is not confident about.

Keep it tight. A wall of text makes every model's answer worse, and costs more.

**Strip anything that should not leave the machine:** customer names, credentials, internal
URLs, proprietary logic. Abstract it ("a dental clinic client", not the name). The script sends
the same text to several vendors at once. If the decision cannot be stated without sensitive
detail, say so and skip the consult.

Write the prompt to a file, show it to the user, and run it only after they confirm.

## 4. Run it

```bash
python ~/.claude/skills/consult/consult.py --dry-run < prompt.txt   # who would be called, rough size
python ~/.claude/skills/consult/consult.py < prompt.txt             # every provider with a key
python ~/.claude/skills/consult/consult.py --models openai,gemini < prompt.txt
```

`--dry-run` calls nobody. It lists the providers and models, the prompt length, and a rough
input token count (about 4 characters per token). Use it to estimate cost before a long prompt:

```
cost per provider = input tokens x input price + output tokens x output price
```

Look up each provider's current price on its own pricing page. Prices are not stored in this
skill because they change. Reasoning models count their thinking as output, so the output side
is usually the larger part. The `CONSULT_MAX_OUTPUT` cap (default 16000 tokens) bounds it.

Calls run in parallel. A slow reasoning model can take several minutes; that is normal.

**Model ids drift.** A 404 or "model not found" almost always means a stale model id, not a
broken key. Check the provider's current model list and set the override env var
(`CONSULT_OPENAI_MODEL`, `CONSULT_GEMINI_MODEL`, `CONSULT_XAI_MODEL`) or edit the table at the
top of `consult.py`. A 401 means the key itself is wrong or expired.

**Manual fallback.** If the user prefers to paste into chat apps (for example to use a
deep-research mode only available in the browser), print ONE fenced prompt block with nothing
else inside the fence, so they copy it once and paste it into each.

## 5. Reconcile

In this order:

1. **Agreed.** Where all answers converge. Highest confidence.
2. **Conflicted.** Name each conflict and say which side you find more credible and why
   (recency, specificity, a source that checks out). **Never average conflicting answers into a
   mushy middle.** The disagreement is usually the most valuable output.
3. **Changes the decision.** Where this moves what you believed going in. Say it plainly.
4. **Still open.** What none of them answered. Sometimes that is the real result.

Then **state the decision and proceed.** The consult exists to unblock the work, not to file a
report. Mention which providers answered and any that failed, so the user knows if a key needs
attention.

Verify before acting on anything load-bearing. Every model can be confidently wrong, a cited
source is not a checked source, and three models agreeing can be three models repeating one
popular error. If a claim decides the direction, confirm it against the real docs or the live
system.

## 6. Stale answers

If answers come back after the work has moved on, check the decision is still open before
acting on them, and say so rather than silently applying advice to a changed situation.

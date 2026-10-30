# NextYes — handoff for the next chat

Read this first. It holds every decision made so far and why. The code in this repo is the source of truth for what is built.

## 1. Context

- **Event:** HUMAIN "Future AI Builders" hackathon, the selection stage for a HUMAIN internship. Solo entry (all participants are individuals).
- **Deadline:** Saturday 31 Oct 2026, 8:00 pm Riyadh time. Aim to submit by 7:00 pm.
- **Submission (all recorded, virtual):** on the event platform — problem, solution, how it works, a presentation and a demo. Presentation 3–4 minutes total: about 2 min of slides (8–10 slides), a 5–10 s motion-graphic intro of the site, then a walkthrough of the live website. Judges may also open the site and click around on their own, so it must explain itself at first glance.
- **Challenge chosen: #3 Autonomous Enterprise.** "Identify a business process that can be aided by AI and autonomy, and build an AI agent that improves that process… take ownership of the business need… complete end-to-end… understand the objective, use available information, and deliver the results with minimal human intervention."
- **Judging criteria (same for all challenges):**
  1. Task performance on unseen / held-out test cases
  2. Robustness & adaptation when conditions, inputs or requirements change
  3. Evaluation & iteration: systematic testing, reproducible improvements, regression checks, proof that each component contributes
  4. Technical judgment & creativity: thoughtful trade-offs, value over simpler alternatives
  5. Engineering quality: reproducible, inspectable, reliable, maintainable
  6. Communication

The criteria are very technical, so the plan is: strong business story + measured results.

## 2. The idea

**NextYes** — an agent that takes a small business from a financing rejection to an approval. It diagnoses why a lender would decline, builds a plan, **executes the steps it can itself**, re-assesses as data changes, prepares the application, and submits it after the owner approves. If the lender declines, it analyses the reasons and loops back to the plan.

- **Customer = the bank** (offers NextYes to its SME clients, e.g. via the HUMAIN ONE agent marketplace). **User = the SME owner.**
- **Opening line for the pitch:** "A bank's no is really a not yet. NextYes takes you from not yet to yes."
- **Why HUMAIN cares:** HUMAIN launched a Banking, Financial Services & Insurance (BFSI) sector (MOZN partnership, Aug 2026). HUMAIN ONE is their agentic enterprise OS with a marketplace for agents. Its public agent list (HR, productivity, procurement NDA manager, project) has no banking or lending agent.
- **Competition and our angle:**
  - MOZN (HUMAIN partner) covers fraud / AML / KYC — we stay out of that.
  - Abwab.ai (Saudi) automates the lender's credit decision and covers the lending cycle; Monsha'at "Tamweel" portal and Lendo match SMEs with funders; Monsha'at "Monshaati 360" gives a static report. None (that we found) coaches a declined business with a plan and follows it to approval.
  - Abroad the idea is proven: FXE/CFIT (UK) found ~65% of 24,000 declined SMEs had "readily fixable" profiles; UK tools give readiness coaching; LendingScore (AU) gives step plans. Say "UK figure" when citing it.
  - In the pitch say "the market focuses on the financing decision, not the path to it" — never claim competitors "can't" do something.
- **Scalability story (future work, foundations exist):** individuals (personal / mortgage) via a new policy file; other products (cards, Kafalah, SME Bank, crowdfunding); real data via open banking, Fatoora, CR, credit bureau; GCC via per-country policies. Vision: a readiness engine for any financial "no".

## 3. Key design decisions (and why)

1. **The language model never decides readiness.** A deterministic rule engine scores the business against a lender policy (YAML). The model extracts, explains, plans and talks. Reasons: banks need explainable, repeatable, auditable decisions. We will *prove* it, not just claim it: baseline B1 = the agent deciding without the engine.
2. **The agent may add observations** outside the rules (e.g. "a large personal transfer last month") as notes for the analyst; they never change the score.
3. **Policies are data.** Swapping the YAML changes the verdict with no code change — our evidence for "robustness & adaptation". Every rule cites a public source; thresholds the source does not quantify are marked `assumption: true`.
4. **Who executes each plan step** (this is how we show "minimal human intervention"):
   - *Agent does it:* collect documents, chase overdue receivables with reminders.
   - *Agent prepares, owner approves with one click:* renew CR, resize the amount to what the engine says is affordable, switch to a better-fitting lender, add a Kafalah guarantee.
   - *Owner does it, agent follows up:* pay down debt, steadier revenue.
   - Often the business is fine and the *application* is wrong (amount too high, wrong lender, no guarantee) — the agent fixes that almost immediately.
   - Metric: share of plan steps executed by the agent.
5. **Orchestration: LangGraph** (the user asked for it; it fits): the journey is a state graph with a loop on rejection; `interrupt` = the approval gate; checkpointing = state across simulated months; the graph picture goes on a slide. Do not use heavy LangChain abstractions; the engine stays plain Python, called as a tool.
6. **Models (Anthropic API):** Claude Haiku 5.5 (`claude-haiku-5-5`) for document extraction and the manipulation check — routine, cheap, fast. Claude Sonnet 5.5 (`claude-sonnet-5-5`) for planning, dialogue and rejection analysis. Log tokens and latency per call; compare with "Sonnet for everything".
7. **Extraction design:** the LLM reads documents and returns *structured rows* (e.g. each bank transaction classified as revenue / opex / debt / owner / personal); **Python does the arithmetic.** LLMs are unreliable at summing ~150 transactions.
8. **Guardrails** — build in the demo: consent screen, approval gate before `submit_application`, refusal of manipulation requests (e.g. "hide my loan from the bank") with a lawful alternative, audit log of every tool call. In code + slides: read-only data tools, escalation to a human advisor, bank sees only the final file. Wording: "designed to align with the PDPL and in-Kingdom hosting" — never "compliant".
9. **Data is synthetic** (real SME financial data is confidential — the same reason we built guardrails). Rules come from public sources; documents mimic real ones; we say it plainly in the pitch.

## 4. What is built (all tests pass: 492)

- **Chunk 1 — Readiness engine** `backend/app/engine/`: models, finance math (instalment, DSCR, max affordable amount, Monsha'at size class), named checks, YAML policy loader, `assess()`, CLI. Policies: `commercial_bank_sme.yaml` (threshold 75) and `digital_lender_invoice.yaml` (threshold 70). Hard blockers block readiness regardless of score.
- **Chunk 2a — Synthetic businesses** `backend/app/synth/` (profiles, issues, generator, dataset): every business starts healthy, then issues are planted; issue codes = policy rule ids. 40 dev, 20 held-out (different seeds and only issue combinations never in dev), 3 demo (bakery supplier, contractor, online store). 6 clean businesses to measure false alarms. `data/<split>/<id>/business.json` + `truth.json` (expected result per policy).
- **Chunk 2b — Documents** (ledger, documents): 6–7 bilingual PDFs per business, marked SIMULATED with invented issuers: bank statement (unlabelled transactions incl. owner injections and personal spending), CR certificate, credit report, receivables aging, tax compliance (e-invoicing + VAT filings), financing application, income statement (only if statements exist). Tests prove the documents reproduce the true data exactly, so measured errors belong to the agent.

- **Chunk 3a — PDF text reader** `backend/app/extract/pdf_text.py` (pdfplumber, no LLM): layout text with columns kept (right-aligned amounts anchored on their right edge), Arabic reversed glyph by glyph so lam-alef ligatures survive, harakat dropped, missing required documents listed in `DocumentSet.missing` (no income statement is a fact, not a gap). Checked on all 63 businesses: 7,591 statement rows, 0 in the wrong Debit/Credit column.
- **Chunk 2c — Difficulty levels** `backend/app/synth/variants.py`: the same documents at three levels, written to `documents/<level>/` with `noise.json`. *clean* = original. *realistic* = three bank layouts (classic debit/credit; one signed amount column with dd/mm/yyyy and references; right-to-left Arabic-only), many wordings incl. abbreviations and Arabic-only rows, individual customers whose transfers look like the owner's own money (the owner's name is now on the CR certificate — the only way to tell them apart), ~30% miss one required document. *hard* = realistic + 1–2 scanned documents (image only) + conflicts: `APP_OPERATING_SINCE` (application claims an earlier start than the CR) and `INCOME_REVENUE_INFLATED` (income statement overstates revenue vs the bank statement); the authoritative document is never the missing one. Dev and held-out wording pools are disjoint (tested). Why: on clean documents a 12-line keyword map gets 100%, so the LLM showed no value; the eval now reports a curve clean → realistic → hard against baselines.
- **Chunk 3b–3d — Extraction** `backend/app/extract/`: `schemas.py` one forced tool per document (prompt version `v1`); `llm.py` `AnthropicReader` (Haiku `claude-haiku-5-5`, override with `NEXTYES_EXTRACT_MODEL`; scans sent as page PNGs; falls back without `temperature` if the model rejects it) wrapped in `CachedReader` (disk cache in `backend/cache/llm/`, keyed by model + prompt version + prompt + document; commit it so judges can reproduce without a key); `assemble.py` reads CR and credit report first and passes the owner's name and lenders to the bank reader, then does all arithmetic in Python, detects conflicts (`APP_OPERATING_SINCE`, `INCOME_REVENUE_INFLATED/UNDERSTATED`) and runs self-checks (`BALANCE_RECONCILES`, `TWELVE_MONTHS_COVERED`, `DEBT_MATCHES_BANK`); missing or unreadable required documents → no snapshot, fields listed as unresolved. `oracle.py` is a perfect reader from the ledger (pipeline ceiling; can plant mistakes). `evaluate.py` scores field accuracy (only where the document was given), verdict agreement per policy (engine on extracted vs true snapshot), missing-document requests, conflict recall / false alarms, tokens and latency → `backend/reports/`. Oracle ceiling = 100% on all levels (tested). **Real Haiku numbers not yet run** — first run on Ahmed's machine.
- **Fix to Chunk 2b:** long table text overflowed into the next column, so some amounts were unreadable even to a person. `Doc.fitted_cell` now shrinks text to fit (min 5.5 pt) and raises if it still doesn't; column widths rebalanced. Demo PDFs regenerated.

Sources used for policies: Lendo — Business financing requirements in Saudi Arabia; Qoyod — SME financing in Saudi Arabia 2026.

## 5. What is next


- **First real Haiku run:** one business first (`python -m app.extract.assemble ...documents/clean`), check the bank lines and the self-checks, then `--limit 3`, then the full dev run per level. Look at `reports/extraction-dev-<level>-haiku.md` → wrong fields → fix prompts in `schemas.py` and bump `PROMPT_VERSION`. Keep a version table of prompt versions vs accuracy (criterion 3).
- **Chunk 4 — Agent:** LangGraph graph (consent → extract → diagnose → plan → execute/approve → advance time → re-assess → prepare → approval gate → submit → result, loop on decline). Tools: `get_financial_data`, `extract_document`, `assess_readiness`, `create_plan` / `update_plan` (plan validator: every blocker covered, no forbidden step), `request_document`, `compile_application`, `match_funder` (pick the policy the business fits), `submit_application` (needs approval), `escalate_to_human`. Simulation: each step has a defined effect on the data; "advance 1 month" applies done steps.
- **Chunk 5 — Evaluation:** `make eval` → report, per level (clean / realistic / hard), with a keyword-rule extractor as baseline B-extract; use `noise.json` to score missing-document requests and conflict flags. Baselines B0 (one prompt, all data) and B1 (agent without engine); ablations (no engine, no validator, no document request); robustness (policy swap, noisy / missing / conflicting documents, mixed language); manipulation set (~30 messages: refusals and false refusals); cost and latency; version table v1 → v2 → v3. Final numbers on held-out only.
- **Chunk 6 — API:** FastAPI, per-session state, rate limit per session.
- **Chunk 7 — Web app:** React + Vite + Tailwind, **English first** (some judges are not Arabic speakers), strings in a translation file, Arabic later if time. The agent replies in the user's language. Screens from the mockup: landing (pick a demo business), consent, journey (score vs threshold, blockers, plan grouped by executor, chat, "advance 1 month", "next step", audit log), approval, bank view, evaluation results. The user wants significant UI changes later and has ideas — ask before building the UI.
- **Deploy:** frontend on Vercel, backend on Render (paid tier so it doesn't sleep). API key server-side only. The user will pay ~USD 40+ in API credits so judges can use it freely.
- **Then:** project page on the platform, slides (8–10), short motion intro, recording.

## 6. How to work with Ahmed

- Reply in **Arabic** (Gulf dialect is fine) until he says otherwise. Code, comments and docs in English.
- **Small chunks** he can review; after each chunk explain in Arabic what every new file does and how to test it.
- **Never commit or push**; he commits under his name. Deliver code as a zip (or files) and give copy-paste PowerShell commands.
- His machine: **Windows, PowerShell, Python 3.11**, VS Code, project at `C:\Users\ahmad\Downloads\nextyes-chunk1\nextyes`, venv `.venv`. `make` is not available — give the plain commands. Run commands one line at a time.
- Repo: `github.com/Ahmed-log11/NextYes` (private for now; make it public before submitting).
- Be honest and direct: he asked to be told plainly if anything should change, small or big.
- He prefers measured results over claims, and dislikes fake data but accepts it here.

## 7. Links

- Plan document (Arabic, partly superseded by this file): https://claude.ai/artifact/PNkcapt7Qsu6UccHbqZXpZ
- UI mockup (first draft, to be reworked): https://claude.ai/artifact/39P26sHRk5z2AAsjNCY8mE
- The original long chat can be searched for details not captured here.

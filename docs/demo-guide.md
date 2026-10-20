# Demonstration Guide

This is a five-to-eight minute demo that covers discovery, verification, composition, execution, tracing, monitoring, failure recovery, document grounding and the Mapper/Auditor adapters.

## Before the demo

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe run.py
```

Open <http://127.0.0.1:8000>. The header should show `Offline demo mode`, the tool count and `Deterministic fallback`.

If the port is busy:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

## 1. Happy path: weather and currency

Click the **Weather + currency** example or paste:

> What is the temperature in Lahore tomorrow, and what is 200 USD in PKR?

Expected behavior:

- Answer includes a Lahore forecast and a USD/PKR conversion.
- The **Ranked candidates** panel has three groups: geocoding, weather and currency.
- Claim badges show verified/supported claims.
- The **Chain plan** shows geocoding -> weather and the independent currency step.
- Link checks are green because `Coordinates (degrees)` feeds the weather provider and currency concepts match.

Talking points:

- The Client is not calling one monolithic LLM. It is retrieving typed tools, checking claims, binding outputs to inputs and executing providers.
- The answer is synthesized from successful branch outputs.

## 2. Traceability

Open **Agent trace**.

Expand `graphrag_shortlist`, `claims_verified`, `candidate_ranking`, `chain_composed` and `step_succeeded`.

Talking points:

- Every event has an actor, sequence number, summary and JSON payload.
- The trace is persisted in SQLite and can be fetched through `GET /api/tasks/{task_id}` or `/messages`.
- This is the evidence for explainability, not a console log that disappears.

## 3. Injected failure and substitution

Open **Monitoring**. Click **Fail next weather call**. The UI schedules one failure and runs the weather/currency demo.

Expected behavior:

- The primary weather provider fails.
- The trace includes `step_failed`, `substitution_requested`, `substitute_selected` and `substitution_succeeded`.
- The plan step is marked `substituted` and names the backup mirror.
- The answer still completes.
- Trust is updated for the failed and substitute providers.
- With the default threshold of two failures, one injected failure may not open the breaker; the substitution still demonstrates recovery.

Talking points:

- Substitution is capability-based and type-checked, not a hard-coded retry.
- The breaker is a separate safety mechanism so a repeatedly failing provider is removed from ranking.

## 4. Drift and an open circuit

Click **Inject weather drift**. The Auditor records a high-severity `DriftAlert` and the Client-to-Open-Meteo link is tripped.

Run the weather task again.

Expected behavior:

- The primary Open-Meteo candidate is ineligible with `circuit breaker open`.
- The backup is selected up front, so the step is not marked as a runtime substitution.
- The monitoring panel shows the drift alert and the open breaker.

Talking points:

- Drift is treated as evidence against a provider, not as a silent schema warning.
- Open breakers are visible in candidate cards and in the monitoring table.

## 5. Trust registry

Still in **Monitoring**, inspect:

- provider trust scores and call counts;
- breaker states;
- drift alerts;
- the trust detail endpoint.

Optionally open:

```text
http://127.0.0.1:8000/api/trust/open-meteo
```

Talking points:

- The score is `(successes + 1) / (successes + failures + 2)`.
- Contradictions have a heavier weight than ordinary call failures.
- The replay check recomputes the score from append-only history.

## 6. Document provider

Open **Documents**.

Upload a small `.txt` file such as:

```text
The demonstration capital is Lahore.
The project uses three provider adapters.
The evaluation includes fifty matching tasks.
```

Ask: `What is the demonstration capital?`

Expected behavior:

- The Client routes the question to `AnswerFromDocument`.
- The answer is extractive and cites the uploaded file.
- No live API is contacted.

You can also ask about the seeded project brief before uploading anything.

## 7. SQL provider

Run:

> How many students are enrolled in the BS Artificial Intelligence program?

Expected answer in the seeded database: students = 8.

The SQL provider is read-only, accepts only safe query templates, and returns a table plus the executed SQL. This is the provider that intentionally has no substitute, so an injected failure produces a clear failure rather than a fake recovery.

## 8. Tool library and correction staging

Open **Tool library**.

- The catalogue shows capability, validation state, claim label and trust.
- Select the adversarial Fahrenheit mock.
- Submit a correction that normalizes `Temperature` from `F` to `C`.
- The correction passes ontology checks and is staged.
- Submit an invalid concept and observe the rejection reason.

Talking points:

- The Mapper adapter validates corrections against the shared ontology before staging them.
- The adversarial mock is intentionally present to show that claim evidence and unit checks matter.

## 9. Evaluation

Run:

```powershell
.\.venv\Scripts\python.exe -m app.evaluation.run_all
```

Show `reports/summary.json` and `reports/matching.json`. Mention that the reports are deterministic offline regression results and that live behavior is a separate manual check.

## 10. Reset

Click **Reset demo state** in Monitoring. This clears trust, breakers, drift alerts, mapper staging, provider failure overrides and cache.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `.env` missing | `Copy-Item .env.example .env` |
| PowerShell activation blocked | Use `.\.venv\Scripts\python.exe ...` directly |
| Port 8000 busy | Run uvicorn on another port |
| Blank UI styling | Check `/static/styles.css` returns 200 |
| Live mode slow or offline | Set `AB_OFFLINE_MODE=true` |
| Old state after experiments | Click **Reset demo state** or delete `data/runtime/` |
| LLM planner not used | Expected; deterministic planning is the default |

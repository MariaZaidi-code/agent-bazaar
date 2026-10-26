# GitHub and VS Code Setup

This repository is already structured for GitHub and VS Code. The remaining steps are local Git initialization and creating the remote.

## Before publishing

Check that generated or private files are excluded:

```powershell
git status --short
```

The `.gitignore` excludes:

- `.venv/`, `__pycache__/`, build output, caches;
- `outputs/*` except `outputs/.gitkeep`;
- `.env` and `.env.*` except `.env.example`;
- local live-probe experiments;
- editor and OS files.

The source PDF and DOCX work-plan files live outside this repository and should not be committed. They are reference material, not project source.

No API key or secret is needed for the default tests, demo, evaluation, or CI.

## Create the local repository

From the project root:

```powershell
cd C:\path\to\agent-bazaar-auditor
git init -b main
git add .
git status
git commit -m "Build Agent Bazaar auditor, drift monitor, mocks, and evaluation"
```

Review `git status` before committing. The expected tracked set includes source, tests, datasets, docs, VS Code configuration, CI, README, license, and `outputs/.gitkeep`. It should not include `.venv`, `.cache`, `__pycache__`, or report outputs.

## Create the GitHub repository

### With GitHub CLI

```powershell
gh auth status
gh repo create agent-bazaar-auditor --private --source . --remote origin --push
```

Use `--public` instead of `--private` if the project should be public. Add a description such as:

```text
Trust and drift auditor for third-party agent tools, with claim verification, DriftAlert, mock providers, and reproducible evaluation.
```

Suggested topics:

```text
ai-agents multi-agent-systems tool-verification drift-detection trust trust-registry python
```

### With the GitHub website

1. Create an empty repository named `agent-bazaar-auditor`.
2. Do not add a README, license, or `.gitignore`; they already exist locally.
3. Connect and push:

```powershell
git remote add origin https://github.com/<your-account>/agent-bazaar-auditor.git
git branch -M main
git push -u origin main
```

If GitHub asks for credentials, use a personal access token or GitHub CLI authentication, not a password.

## Verify CI

The workflow is `.github/workflows/ci.yml`.

It runs on pushes and pull requests to `main`, and can be started manually. It tests:

- Ubuntu and Windows;
- Python 3.11 and 3.13;
- Ruff;
- Pytest;
- the full claim, drift, and trust evaluation;
- upload of the generated evaluation reports as a workflow artifact.

A green run means the package installs from `pyproject.toml`, the tests pass without network access, and the evaluation still reaches the expected labels and detections.

If a job fails:

1. open the failed step;
2. run the same command locally in a clean `.venv`;
3. check whether a test depends on local state under `outputs/` or `.cache/`.

## Recommended repository settings

- **Description:** use the one-line description above.
- **Topics:** add the suggested topics.
- **Default branch:** `main`.
- **Branch protection:** require the CI workflow before merging to `main`.
- **Actions permissions:** allow GitHub Actions to run workflows, with read-only repository contents.
- **Secrets:** none are required. If live LLM evaluation is added later, store keys under Actions secrets and never in `.env` or source.
- **Releases:** tag the submitted version, for example `v1.0.0`, after the final demo and report are frozen.
- **Pages:** not required; this is a CLI/API project, not a static site.

## VS Code

Open the folder:

```powershell
code C:\path\to\agent-bazaar-auditor
```

Recommended extensions are declared in `.vscode/extensions.json`:

- Python;
- Pylance;
- Ruff.

### Interpreter

The workspace setting points at:

```text
.venv\Scripts\python.exe
```

If VS Code does not select it automatically:

1. run **Python: Select Interpreter**;
2. choose `.venv\Scripts\python.exe`;
3. open a new integrated terminal.

On macOS or Linux, change the interpreter path in `.vscode/settings.json` to `.venv/bin/python`.

### Tasks

Run **Tasks: Run Task**, then choose:

- **Auditor: Install dev dependencies**
- **Auditor: Run tests**
- **Auditor: Lint**
- **Auditor: Demo**
- **Auditor: Evaluate**
- **Auditor: Serve mock API**

### Debug configurations

The Run and Debug view includes:

- Auditor: Demo
- Auditor: Evaluate
- Auditor: Serve API with mocks
- Auditor: Verify Open-Meteo offline
- Pytest: Current file

### Testing

The Test Explorer uses pytest with `tests/` as the test path. You can run all tests or a single test file from the gutter.

## CI command parity

Run the same checks locally:

```powershell
python -m ruff check .
python -m pytest -q
python -m agent_bazaar_auditor evaluate
```

The evaluation does not use the network. It writes reports under `outputs/reports/`, which remains gitignored. Commit documentation updates to [the Auditor evaluation](evaluation.md) when the numbers change intentionally.

## Publish checklist

- [ ] `python -m ruff check .` passes.
- [ ] `python -m pytest -q` passes.
- [ ] `agent-bazaar-auditor demo` completes.
- [ ] `agent-bazaar-auditor evaluate` matches the committed snapshot.
- [ ] README links resolve.
- [ ] No `.venv`, cache, report, secret, or source PDF/DOCX file is staged.
- [ ] `LICENSE` and author name are correct.
- [ ] CI is green on GitHub.
- [ ] Repository description and topics are set.
- [ ] Tag the submitted version.

# Local model smoke evaluation

Evaluated on November 13, 2026 using the user's installed LM Studio
`muse-glimmer-30b` model (Muse Glimmer, Q6_K_XL), exposed temporarily as
`report-agent-eval`, with a 32,768-token context. No model was downloaded.
All prompts, sample reports, and database rows were synthetic.

| Scenario | Observed result |
| --- | --- |
| User unsure what report they need | Read the discovery skill, asked about purpose, and offered concrete choices without prematurely creating a template |
| Reuse accepted report for October in Europe | Inspected the saved definition and proposed exactly `2026-10-01`, `2026-11-01` (exclusive), and `Europe`; did not create a replacement template |
| Build a report from a sample and SQLite data | Read sample/template/DOCX skills, inspected the contract, previewed query data, created a valid definition, and rendered a DOCX preview |
| Accept and rerun the model-authored template | Application acceptance persisted the template; November's run returned 150/110 instead of October's 120/90 using the same saved query |

The first two passing cases are recorded locally in
`output/agent_evals/82a5f8adab6949a4a9c6ab026145b9b8/results.json`.
The authoring case is recorded in
`output/agent_evals/93af2a6a8832489dbb65fcaff9c5b57f/results.json`.
These generated artifacts are intentionally outside version control.

This is a smoke evaluation, not a model benchmark. It does not establish reliability
across arbitrary sample documents, layouts, databases, languages, or other models.
Smaller models have not yet been evaluated. Onboarding used more model/tool turns
than repeat-run preparation; confirmed execution itself made no model calls.

Reproduce with `tests/agent_evals/live_lmstudio.py --model MODEL_ID --authoring`.
Use `--authoring-only` to run the template/query creation case separately.

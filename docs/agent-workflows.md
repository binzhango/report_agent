# Conversational report authoring

The optional agent service uses Deep Agents and the repository's `.agents/skills`
directory. The framework discovers skills and reads their instructions on demand;
there is no custom skill loader. The application exposes report-specific tools,
and the existing rendering engine continues to produce the final files.

The [system prompt](../src/report_agent/agent/prompt.py) defines Report Studio's role,
workflow routing, required next steps, and failure recovery. The agent factory passes
it to Deep Agents through `system_prompt`; `skills=["/"]` still uses the configured
skills backend for normal framework-managed skill discovery. Skills provide the
detailed procedures within each workflow.

For a known report type without a selected design, the prompt directs the agent to
establish audience and format, render examples, and get a design choice before
asking detailed data-binding questions. Uploaded references, agreed structures,
resumed drafts, and accepted reports have their own paths. A missing converter
blocks rendering: the agent should explain it and offer recovery or an explicitly
agreed text-only outline, rather than silently advancing past design selection.
These are model instructions, not a new application state machine or a guarantee
of identical responses. Restart the service and start a new chat when evaluating
prompt changes; existing agent instances retain the prompt used at creation.

## Start the service

```sh
uv sync --locked --extra agent
export OPENAI_API_KEY='your-key'
export REPORT_AGENT_MODEL='your-tool-capable-model'
# Optional for another OpenAI-compatible service:
# export OPENAI_BASE_URL='http://127.0.0.1:8000/v1'
uv run --extra agent report serve
```

Open the localhost address printed by Gradio. The default is port 7860.
The interface is a single conversation thread: previews, downloads, parameter
cards, and approvals appear inline. Use **＋ Attach** and **Saved reports**
below the composer for files and reusable reports. Tool activity and completed
artifacts appear while the agent works; final assistant text appears when its turn
completes. Older cards remain visible, with superseded actions disabled.
For ready-to-upload files and configured fictional database sources, use the
[runnable conversation kit](../examples/conversations/README.md).
The model must support tool calling. There is no hard-coded model choice and no
assumption that a particular small model will follow all onboarding instructions.
Set `REPORT_AGENT_TIMEZONE` for relative-date interpretation (default:
`America/New_York`). `.env.example` lists variables; `.env` is not loaded implicitly.
`REPORT_AGENT_TIMEOUT` and `REPORT_AGENT_MAX_TOKENS` configure request timeout and
the output-token bound (defaults: 120 seconds and 4096 tokens).

For LM Studio, start its local server and select/load a tool-capable model. Set
`OPENAI_BASE_URL=http://127.0.0.1:1234/v1`, `OPENAI_API_KEY=lm-studio` when local
authentication is disabled, and `REPORT_AGENT_MODEL` to its model identifier.
The opt-in live evaluation uses synthetic content only:

```sh
uv run --extra agent python tests/agent_evals/live_lmstudio.py \
  --model YOUR_LOADED_MODEL_ID --authoring
```

It checks guided discovery, parameter extraction for an accepted report, and
optional creation of a new query-backed template followed by a refreshed run.
Results are retained in `output/agent_evals/`. This is a smoke evaluation, not a
claim of broad model reliability.
See the [recorded local evaluation](agent-evaluation.md) for observed results.

Install `texres` for PDF and LibreOffice's `soffice` for Office reports. Install
Poppler's `pdftoppm` for image previews. Without Poppler, report downloads still
work. The model receives chat messages, extracted sample text, and explicitly
requested data previews. API credentials remain in the server environment.

## Onboard once

See [three example conversations](conversation-examples.md) for complete onboarding
and repeat-run dialogues for each starting point.

- **Uncertain user:** describe the intended outcome. The agent asks focused
  questions, proposes an outline, and offers rendered examples.
- **Known report type:** ask for a report, choose from rendered examples, then
  establish the actual fixed content and data bindings.
- **Uploaded sample:** upload PDF, DOCX, PPTX, or XLSX (also TXT/Markdown). The
  agent uses text, section/slide/sheet boundaries, and limited design cues to
  create a new layout. It does not reproduce exact formatting or perform OCR.

For tables and charts, establish the source, columns, date range, filters, and
calculations during onboarding. Upload CSV/XLSX or configure a server connection.
The agent can preview a query's first five rows before binding it. Fixed narrative
is saved in the template and is not requested again on every run.

Ask for revisions until the preview is satisfactory. **Accept template** saves
the current successfully previewed draft as an immutable accepted version.
A revision requires a new preview. Example reports are explicitly labeled as
demonstrations; replace their illustrative content during onboarding.

## Repeat quickly

Ask for an accepted report using new parameters, such as October sales for Europe.
The agent reads the saved definition, uses defaults, and asks only about missing
or ambiguous values. After it prepares a run, inspect the parameter table and
press **Confirm parameters and render**. The application fetches data and renders
the report without a further model call. Sending another chat message invalidates
the previous pending confirmation so stale parameters cannot be submitted.

Use the CLI for unattended execution of accepted definitions:

```sh
uv run --extra agent report run accepted/monthly_sales/v1 \
  --parameters october.json --connections connections.yaml
```

The CLI takes explicit parameter values as authorization for that run; it does
not prompt or contact the model. See [report definitions](report-definitions.md).

## Storage and deployment

This is a **single-user local service**. Every chat shares the same configured
sources, uploaded workbooks, and report library, including uploads from earlier
chats. Chat IDs separate conversation state, not data access. Do not expose one
instance to multiple users expecting private workspaces. Multi-user deployment
requires authentication and per-user source, storage, and template isolation.

Gradio serializes report interactions with a shared concurrency group limited to
one worker. Registry and per-session locks protect lookup and turns; shared source
mutation and UI snapshots rely on that serialized execution. The service is not a
general thread-safe API for independent concurrent callers.

`report_library/drafts/` contains working bundles. Accepted bundles are stored at
`report_library/accepted/<id>/v<N>/` with `report.yaml`, engine metadata/source, and
a sample report. Run records and artifacts are under `output/runs/<run-id>/`.
Uploaded data is copied to `report_library/sources/` and retained for repeat runs;
its random connection name remains stable across service restarts. These directories
are ignored by Git. Keep durable copies of accepted bundles and their source data.

Conversations use Deep Agents' in-memory checkpointer and expire with the Gradio
session or server process. Accepted templates and uploaded data persist on disk.
Template access control, authentication, distributed storage, and scheduled runs
are not implemented in this first local service.

Deploy the `.agents/skills` directory alongside the application. If running from
an installed wheel outside the checkout, point `REPORT_AGENT_SKILLS` to that
directory explicitly; the wheel does not silently install or discover host skills.

## Current authoring boundaries

The generated-layout schema supports ordered text, table, and chart blocks,
headings, accent colors, sans/serif typography, orientation, and document page
breaks. PDF uses LaTeX; Office uses generated Flat ODF through LibreOffice.
PPTX creates a cover and one slide per block. XLSX creates a narrative sheet and
dedicated data sheets, and currently supports only text/table blocks.

This initial compiler does not reproduce arbitrary sample designs, custom slide
geometry, mixed page orientations, workbook formulas, native Excel charts, or
custom per-cell formatting. The original renderer's hand-authored templates retain
their existing capabilities. Reusable generated narrative from query results is
also not yet part of the report-definition schema; fixed narrative and parameter
substitutions are supported. Visual previews and native Office review remain
necessary; length/row limits are not a complete layout-quality guarantee.

The application has no generic shell or delegation tool. Domain tools perform
template compilation, query execution, preview generation, and storage. Model
execution is bounded; validation and rendering are deterministic.
Harness policy is registered once per model at service initialization (or lazily
for direct agent construction), explicitly excluding `task` and filesystem writes.
Tool failures return fixed public messages and structured validation fields;
exception strings and renderer diagnostic messages stay out of model responses.
Full renderer diagnostics remain in local run artifacts for operator inspection.

## Verification

```sh
uv run --extra agent --extra parquet ruff check .
uv run --extra agent --extra parquet ruff format --check .
uv run --extra agent --extra parquet pytest -q
uv run --extra agent python examples/report_definitions/render.py
```

Automated tests cover real document conversion and deterministic model transports;
they do not contact a live provider or remote database. The separate opt-in
LM Studio script exercises a live model with synthetic data. Evaluate the chosen model on uncertain-user onboarding, sample
analysis, data binding, and repeat-run parameter extraction before relying on it.

Framework references: [Deep Agents skills](https://docs.langchain.com/oss/python/deepagents/skills)
and [agent construction](https://reference.langchain.com/python/deepagents/graph/create_deep_agent).

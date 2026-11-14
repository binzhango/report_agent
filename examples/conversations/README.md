# Runnable conversation examples

All records in this kit are fictional. Start from the repository root.

```sh
uv sync --locked --extra agent
export OPENAI_BASE_URL=http://127.0.0.1:1234/v1
export OPENAI_API_KEY=lm-studio
export REPORT_AGENT_MODEL=YOUR_LOADED_MODEL_ID
# For Muse Glimmer's report onboarding:
export REPORT_AGENT_REASONING_STRENGTH=low
uv run --extra agent python examples/conversations/serve.py
```

Load a tool-capable model in LM Studio and enable its local server. Use at least
32,768 tokens of context for multi-turn authoring: skills, tool definitions, source
schemas, and the report schema consume context in addition to chat messages.
The earlier short smoke tests did not establish reliability with an 8,192-token
context. The model's advertised maximum is different from its loaded context.

For Muse Glimmer, `REPORT_AGENT_REASONING_STRENGTH=low` supplies its documented
system-prompt reasoning control. Other models can leave this unset. See the
[model's reasoning guidance](https://huggingface.co/meta-models/Muse-Glimmer-30B-GGUF/blob/main/README.md).
The app streams provider responses internally so a long generation does not wait
for the entire completion before receiving network data. Onboarding may still take
minutes on local hardware; repeat-run rendering does not call the model after
parameter confirmation.

Open <http://127.0.0.1:7860>. If another service uses that port, add `--port 7862`.
This launcher uses isolated storage in `output/conversation_demo/` and configures
two local SQLite connections, `sales_db` and `support_db`. It does not use production
databases. `report serve` still runs normally with your own configured connections.

## Files to upload

| File | Where to use it | Contents |
| --- | --- | --- |
| [milestones.xlsx](milestones.xlsx) | ＋ Attach → Report data | Milestones sheet; Atlas and Beacon, October and November 2026 |
| [sales-example.docx](sales-example.docx) | ＋ Attach → Reference document | Introduction, product table, regional chart, and old commentary |
| [milestones.csv](milestones.csv) | Alternative report-data upload | Same records as the workbook |

The links above provide the source files. In **＋ Attach**,
**Use sales sample** and **Use milestone data** add them directly to the current
conversation, without downloading and uploading them again.
Uploads are inspected locally and acknowledged immediately. Continue in chat with the report content and selection rules; no model call is needed just to add a file.
Use **New chat** at the top between scenarios. All generated previews, downloads,
parameter proposals, and approval actions appear inline in the conversation.

## Try each path

Follow the [three conversations](../../docs/conversation-examples.md). The agent's
wording and question order can vary. Supply answers to its actual questions rather
than expecting an exact transcript.

1. **Sample → PDF:** Upload `sales-example.docx`. Keep the introduction, product
   table, and regional chart; remove old commentary. Choose PDF and blue headings.
   Use `sales_db`, table `sales`, with `order_date`, `region`, `product`, `revenue`.
   Preview October 2026 / Europe, accept, then run November 2026 / Europe.
2. **Known report → DOCX:** Request a project update for department managers and
   rendered Word examples. Choose Project update. Upload `milestones.xlsx` as data.
   Keep a fixed introduction; show milestone, owner, due_date, status, filtering by
   project and due-date range. Preview Atlas / October 2026, accept, then run Atlas /
   November 2026.
3. **Discovery → PPTX:** Describe a weekly support meeting without prescribing a
   report. Explain that team leads need to prioritize unresolved tickets. Choose
   slides, a purpose statement, a ticket table, and counts by priority. Use
   `support_db`, table `tickets`. Include only the selected team's tickets created
   in the period, excluding Resolved and Closed. Preview Billing / November 2–8,
   2026, accept, then run November 9–15.

For dates, the saved queries use an inclusive start and exclusive end. For example,
November 2–8 becomes `2026-11-02` to `2026-11-09`.

## Check the output

- Atlas / October: Design approval, API integration, Security review. No Beacon row.
- Atlas / November: Pilot launch, Training complete, Release sign-off. No October row.
- Europe sales: October Core 12,450 and Plus 8,380; November Core 14,890 and Plus 9,730.
- Regional chart: October Europe 20,830 and Asia 15,670; November Europe 24,620 and Asia 18,120.
- Billing / November 2–8: Duplicate invoice, Payment retry, Receipt missing.
- Billing / November 9–15: Tax correction, Card declined, Export receipt. No resolved,
  closed, or Platform tickets. High priority precedes Medium, then Low.

Accepted templates persist under the demo library. After restarting, select one
from **Saved reports** below the composer, then send the prepared message. **Refresh library**
updates this list after accepting a new template.
The list also includes working drafts. Select a draft to resume its saved layout
and bindings; render a new preview before accepting it. Chat history itself remains
session-local. An accepted report may use inclusive or exclusive end-date rules;
review the parameter proposal against its saved definition.

See the [browser verification record](../../docs/gradio-verification.md) for the
observed passes and the paths that have not yet completed full live qualification.

`prepare.py` can recreate the reference DOCX and create the database. It needs the
same report-rendering dependencies as the app. The checked-in workbook and DOCX
are ready to upload; no generation step is necessary for normal testing.

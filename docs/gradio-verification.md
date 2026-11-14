# Gradio browser verification

## Single-conversation interface update

The UI now uses one chronological thread and one bottom composer. Tool activity,
report galleries, downloads, and parameter proposals are inserted into the thread.
Approvals are attached to the relevant report/parameter card. Earlier artifacts
remain visible, while superseded actions are disabled and checked again by the server.
The assistant's final text appears at completion; internal model reasoning is not
shown. Tool-completion events can display a report before the final text arrives.

Browser checks exercised a workbook acknowledgement, resumed sales draft preview,
inline acceptance, a November parameter card, inline confirmation, and the resulting
PDF/download in the same thread. Unit tests also verify intermediate artifact
updates, immutable history snapshots, and superseded parameter cards.

The composer has aligned **Attach**, **Saved reports**, and **Send** controls.
Attachment/library popovers open above it, are mutually exclusive, and dismiss with
Escape or an outside click. At 390px, the page width stayed 390px and all three
controls measured 36px high. The transcript and rendering pipeline use the same
report services verified below.

## Report workflow qualification

All three starting points completed in Gradio using fictional data, one local Muse
Glimmer model instance, a 32,768-token context, and one inference slot. These are
observed assisted workflows, not a claim of universal or one-shot model reliability.
The agent's wording and question order differ from the illustrative conversations.

| Starting point | Browser actions verified | Refreshed output checked |
| --- | --- | --- |
| Uploaded sales sample → PDF | Add DOCX, confirm content/source rules, preview October, accept, confirm November inputs, render | Europe Core 14,890; Plus 9,730. October values absent; fixed introduction preserved. |
| Known project report → DOCX | Render design examples, select Project update, upload milestones.xlsx, preview Atlas/October, resume draft, accept, confirm November inputs, render | Pilot launch, Training complete, Release sign-off; no October or Beacon rows. |
| Guided discovery → PPTX | Ask purpose/audience, specify support-review content, render designs and draft, revise team binding and heading, accept, confirm next week's inputs, render | Tax correction, Card declined, Export receipt; no previous-week, closed, or Platform tickets. |

## Evidence

Accepted repeat-run records under `output/gradio_verification/runs/`:

- PDF: `0beef2990ea64e44b30f205a17281a8e/run.json`
- DOCX: `4d23be2f03f34f19830e951b833cc304/run.json`
- PPTX: `3d768a3ccd1c4ae18f5dc657e3b9bf33/run.json`

The downloaded files were inspected semantically and their previews reviewed.
The DOCX accepted definition matched its authored draft, with unchanged layout,
fixed introduction, and query bindings. Repeat confirmation runs application code
without a further model call, and replaces the preview/download with the new result.

Recheck all three actual downloads:

```sh
uv run --extra agent python tests/agent_evals/verify_gradio_artifacts.py \
  output/gradio_verification
```

Results are written to `output/gradio_verification/verification.json`. This check
fails if any scenario lacks a matching accepted repeat-run artifact. These output
directories are ignored by Git. See the [runnable kit](../examples/conversations/README.md)
to recreate the flows with checked-in files and isolated demo connections.

## Problems found and corrected

- Supplied the missing workbook, reference DOCX, and fictional database launcher.
- Replaced the unstructured UI with a responsive conversation/review workspace,
  source and example tabs, next-step guidance, progress messages, and saved reports.
- Made file uploads inspect locally and acknowledge immediately without a model call.
- Enabled acceptance only for a successful current preview and rendering only for
  a prepared parameter proposal. Uploads invalidate a pending proposal.
- Added draft recovery after reconnecting. Recovery requires a fresh preview before
  acceptance; the draft list shows the latest revision of each report.
- Applied selected source columns to rendered tables and refreshed gallery images
  after repeat runs.
- Replaced internal reference names in normal responses and hid unrequested SQL.
- Reported empty model completions and context/step-limit failures as errors.
- Raised the bounded agent step limit from 40 to 80: a legitimate authoring sequence
  exhausted the former limit immediately before executing create_draft.
- Replaced a deprecated pandas workbook-inspection call exposed by the new upload test.

Desktop and narrow layouts were inspected. At a 390-pixel viewport the document
width was 390 pixels, with no horizontal overflow. A screenshot of the successful
DOCX workspace is saved at `output/ui_review/report-studio.jpg`.
The final desktop interface is at `output/ui_review/report-studio-desktop.jpg`.
After restarting the service, all three accepted templates were visible in its
saved-template dropdown. Final checks: **238 passed, 1 skipped**, Ruff clean,
formatting clean, and no whitespace errors.

## Review and model limitations

The milestone model draft initially used string parameters with a date-order rule;
validation rejected it and the agent repaired it. The sales draft required repairs
for an undeclared binding and an invalid date/region order rule. The support draft
initially embedded Billing in SQL; review changed this into a required team parameter
bound in both queries and confirmed a generic heading before acceptance. No invalid
draft was accepted. These repairs are part of the observed onboarding flow.

Date semantics are saved with each definition. The sales example uses an inclusive
start and exclusive end. The generated project/support definitions use inclusive
end dates, which were displayed and confirmed; November's project end was November
30, rather than December 1. Follow the saved rules when reproducing a run.

Local onboarding can take several minutes. The loaded GGUF chat template appended
`Reasoning strength: high` even when the application supplied low, so the optional
prompt control did not establish lower latency for this model file. The earlier 8K
instance returned an empty answer during long authoring. Only one 32K instance was
used for the completed qualification flows.

Sample layout is interpreted, not copied exactly. Fixed text and parameter
substitutions are supported; refreshed narrative analysis and OCR remain outside
the implementation. Chat history is session-local; drafts, accepted templates, and
uploaded sources persist on disk.

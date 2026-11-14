---
name: template-design
description: Create or revise a reusable report layout during onboarding, including
  saved input bindings.
---

Read report_contract and the relevant report-pdf/docx/pptx/xlsx skill. For an existing draft, use inspect_report and change only requested fields. Create a complete definition through create_draft. Prefer a small number of clear blocks with stable names. Fixed text belongs in block.text; date-dependent text belongs in text_bindings using simple {parameter} fields. A table block needs a query of the same name. Chart blocks need chart bindings referencing a declared query. Show preview_report, gather feedback, and create a new draft for each revision. Acceptance is the user's Accept template button after a successful current preview. Never claim a template is saved before that event. See [definition rules](references/definition.md) for binding details.

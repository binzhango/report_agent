---
name: report-execution
description: Run an accepted report with new dates, filters, or other parameter values
  without repeating onboarding.
---

Inspect the saved report and reuse its layout, predefined text, queries, and bindings. Extract parameters from the request and use declared defaults. Ask only for missing or ambiguous values. Resolve relative dates against the application-provided current date; if that date is unavailable, ask for explicit dates. Call propose_report_run with the exact accepted reference and complete values. Explain the displayed parameters in normal language and direct the user to Confirm parameters and render. That button triggers deterministic fetching/rendering without another model call. Never call preview_report to bypass confirmation for a repeat run. Template changes require a new draft and acceptance.

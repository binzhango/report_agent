# Three report conversations

These illustrative conversations describe the intended user experience, not recorded
model transcripts. Names, sources, and data are fictional. Messages may vary by
model; previews, acceptance, and parameter confirmation are application actions.

| Starting point | Conversation | Saved result |
| --- | --- | --- |
| User has a sample document | [1. Adapt an uploaded sample](#1-adapt-an-uploaded-sample) | A new layout based on the sample, with confirmed content and data bindings |
| User knows the report type | [2. Choose a report from rendered examples](#2-choose-a-report-from-rendered-examples) | A selected design adapted to the user's content and source |
| User does not know what report to create | [3. Build a report step by step](#3-build-a-report-step-by-step) | An agreed purpose, outline, design, and reusable report definition |

Each conversation includes the longer first-time onboarding and a short later run.
The accepted definition stores the layout, fixed text, parameter definitions, and
data bindings. Subsequent runs change parameter values and fetch fresh data.

**To reproduce these flows:** use the [runnable example kit](../examples/conversations/README.md).
It supplies `milestones.xlsx`, `sales-example.docx`, and a launcher that configures
the fictional sales/support databases. In Gradio, use **＋ Attach**
below the composer to add a reference document, report data, or the supplied examples.
Previews, downloads, and approval controls appear in the conversation.
The regular service does not automatically
configure the example databases. Follow the agent's actual questions; these are
illustrative exchanges, not guaranteed verbatim responses.

## 1. Adapt an uploaded sample

### First-time onboarding

**User:** I uploaded our old monthly sales report, `sales-example.docx`. I want a
new report like this for Europe.

**Agent:** The sample has an introduction, a sales table, and a regional comparison
chart. I can use that structure to create a new layout. Should the new report keep
those sections, or do you want to change anything?

**User:** Keep them. Use a blue heading style and PDF output. Keep the standard
introduction, but remove the old commentary about last year's results.

**Agent:** I'll keep the standard introduction and leave out that commentary. The
table and chart need current data. Which source should supply the sales records?
You can upload CSV/XLSX data or use a configured connection.

**User:** Use our configured sales database. It has order date, region, product,
and revenue. The table should show revenue by product, and the chart should compare
regions.

*The agent inspects the configured source before proposing the bindings.*

**Agent:** I found those fields. For the table, I'll total revenue by product for
the selected region. For the chart, I'll total revenue by region across all regions
for the same period. What period should we use for the first preview?

**User:** October 2026. Yes, the chart should include all regions.

**Agent:** The preview will use October 1 through October 31, 2026, with Europe
selected for the product table. Here is a small data preview from the source.
Does the revenue field represent USD, and should it include every sales record?

**User:** Yes, USD and all records. Those sample totals look right.

*The agent binds both queries, creates a draft layout, and renders a PDF preview
using the source data.*

**Agent:** Here is the PDF preview. The introduction is fixed text. The table and
chart will refresh from the database each time you run the report. Future inputs
will be the date range and the table's region.

**User:** Put the chart on a new page and make the title “Monthly Sales Review.”

*The agent updates the draft and renders a new preview.*

**Agent:** The updated preview is ready. If it looks right, select **Accept template**
to save this version for future reports.

**User action:** Selects **Accept template**.

**Application:** Saves the accepted template and its parameter definitions, fixed
introduction, source bindings, and preview.

### A later run

**User:** Generate the Monthly Sales Review for November 2026, Europe.

**Agent:** Please confirm these inputs for the saved report:

| Parameter | Value |
| --- | --- |
| Start date | November 1, 2026, inclusive |
| End date | December 1, 2026, exclusive |
| Region for the product table | Europe |

**User action:** Selects **Confirm parameters and render**.

**Application:** Queries the source using the confirmed values, renders the saved
layout, and provides the PDF download. It does not ask again about the introduction,
chart design, or data bindings.

## 2. Choose a report from rendered examples

### First-time onboarding

**User:** I need a monthly project status report.

**Agent:** Who will read it, and do they need an editable document or a final PDF?

**User:** Department managers. An editable Word document.

**Agent:** Here are three rendered DOCX examples to compare: Executive brief,
Project update, and Research report. Their contents are demonstration data.
Which structure is closest to what you need?

*The interface shows rendered preview images and downloadable examples, rather
than only template names.*

**User:** The project update. Keep the introduction and milestone table. We don't
need a chart.

**Agent:** I'll use that structure and its standard introduction. What source should
fill the milestone table, and which columns should appear?

**User:** I uploaded `milestones.xlsx`. Show milestone, owner, due date, and status.
Filter by project and the month the milestone is due.

*The agent inspects the uploaded workbook's sheets and columns.*

**Agent:** The Milestones sheet contains those columns, plus a project column. I'll
use project and due-date range as report inputs. Which project and month should
the first preview show?

**User:** Atlas, October 2026.

**Agent:** Here are a few matching rows. The report will include milestones due in
October, including completed milestones. Is that the content you want?

**User:** Yes. Keep completed ones too.

*The agent creates the bindings and renders a DOCX preview using the uploaded data.*

**Agent:** Here is the preview. The title and period use the report inputs, the
introduction stays fixed, and the table comes from the workbook. You can request
changes or select **Accept template**.

**User action:** Selects **Accept template**.

**Application:** Persists the accepted template and its workbook binding. The
uploaded workbook is retained as the source for later runs.

### A later run

**User:** Run the project update for November 2026.

**Agent:** Which project should I use?

**User:** Atlas.

**Agent:** Please confirm Atlas, November 1 inclusive through December 1 exclusive,
2026, using the saved milestone workbook.

**User action:** Selects **Confirm parameters and render**.

**Application:** Filters the retained workbook and produces the DOCX report. This
example assumes that the workbook already contains November rows; changing the
date parameter does not add new records to an uploaded file.

## 3. Build a report step by step

### First-time onboarding

**User:** I need something to help with our weekly operations meeting, but I don't
know what the report should look like.

**Agent:** Who attends the meeting, and what decision should the report help them
make?

**User:** Support team leads. They need to decide which unresolved tickets need
attention.

**Agent:** We could start with a brief purpose statement, a table of unresolved
tickets, and a chart showing unresolved tickets by priority. Would that help, or
is the meeting focused on something else?

**User:** That would help. We also need to see who owns each ticket.

**Agent:** I'll include the owner in the table. Do you present this in the meeting,
share it as a document, or work with the data in a spreadsheet?

**User:** We present it. Slides would be best.

**Agent:** Here are rendered slide examples with demonstration content. We can use
the project-update structure for a short deck: a cover, a purpose slide, a ticket
table, and a priority chart.

**User:** That structure looks good. Use the blue style.

**Agent:** I'll use this standard purpose text: “Review unresolved support tickets
and agree on ownership and next actions.” Where should the ticket data come from?

**User:** Our configured support database. It includes created date, team, title,
owner, priority, and status.

*The agent inspects the source fields.*

**Agent:** For the first version, should the table show all unresolved tickets or
only tickets created in the selected period?

**User:** Only those created in the selected period, for the selected team.
Resolved and closed tickets should be excluded.

**Agent:** I'll show title, owner, priority, and status, ordered by priority. The
chart will count all matching unresolved tickets by priority. To keep the slide
readable, the table can show the first ten matching tickets, labeled as such.
Would that work?

**User:** Yes. Preview it for the Billing team, November 2 through November 8, 2026.

*The agent previews source rows and then renders the PPTX with those bindings.*

**Agent:** Here is the deck preview. The date range includes November 2 through
November 8. The table is labeled “Top 10 unresolved tickets,” and the chart includes
all matching tickets. The purpose statement will stay fixed in later reports.

**User:** Change the heading to “Weekly Support Review.” Everything else looks good.

*The agent changes the heading and renders a fresh preview.*

**Agent:** The updated preview is ready. Select **Accept template** to save this
report for future meetings.

**User action:** Selects **Accept template**.

**Application:** Saves the accepted deck layout, fixed purpose text, queries,
selection rules, and date/team parameters.

### A later run

**User:** Create the Weekly Support Review for Billing, November 9–15, 2026.

**Agent:** Please confirm Billing, November 9 inclusive through November 16 exclusive,
2026.

**User action:** Selects **Confirm parameters and render**.

**Application:** Fetches current matching tickets and renders the PPTX using the
accepted design. No discovery or template design questions are repeated.

## Behavior shared by all three paths

- Onboarding establishes the content and data semantics, not just the visual layout.
- Predefined text can be reused without asking about every sentence. Users can
  still request edits before acceptance.
- Data-dependent sections require a real source and confirmed selection rules;
  demonstration data is clearly identified in example previews.
- Only an explicitly accepted, successfully previewed draft becomes a reusable
  template. Layout or binding changes require a revised draft and acceptance.
- Repeat runs collect missing or ambiguous inputs, present parameters for
  confirmation, and then fetch and render through application code.

The examples cover PDF, DOCX, and PPTX outputs. XLSX follows the same conversation
flow, with the current generated layout supporting text and tables. Uploaded samples
provide structure and content cues rather than exact layout replication. Fixed text
and parameter substitutions are supported; automatically rewriting analysis from
fresh query results is outside the current implementation.

See [agent workflows](agent-workflows.md) for setup and implementation boundaries,
[report definitions](report-definitions.md) for the saved contract, and
[data connectors](data-connectors.md) for source configuration.

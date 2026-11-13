# Blueprint Evidence

**Status:** Draft for Junction 2026. The scope below is proposed for team review.

## Challenge

Stoa · Make Blueprints Talk. Stoa scores answer accuracy, evidence visualization, creativity, and low inference cost at 25% each. [Official challenge](https://hackjunction.app/participate/45/challenges/335)

## Problem and user

A site engineer answering a quantity question has to find the right sheet or model, confirm the scope, and check the counted items. Blueprint Evidence accepts natural-language questions and lets the engineer inspect the exact PDF rows or IFC objects used to calculate an answer.

## Two-minute demo

1. Open the Esplanades BIM model and ask how many doors are on storey `2.korrus`. Answer **42**, isolate the storey, and highlight the 42 doors. Let the judge switch the query to windows or pick another storey.
2. Click a highlighted door to inspect its IFC identity and source storey. The list, count, and highlights come from the same set of elements.
3. Open the A-801 door schedule from a separate project. Ask for A1 doors and get **14** with clickable source rows. Ask for all doors and show why the total is **38**, including two rows whose door type is blank.

## Prototype scope

- Support one official IFC building and text-based PDF door schedules. The IFC view supports door and window counts for a storey or the whole building. The PDF view supports all door marks, counts by type, and the rows behind each result.
- Use IfcOpenShell to extract IFC data and export a GLB for interactive rendering in Three.js. Use pdfplumber for the PDF table and source coordinates. A validated query selects the records, and application code calculates the count.
- Start with predictable query patterns and add model-based interpretation for free-form questions. Ask for clarification when a requested floor, sheet, or type cannot be resolved. The proposed technical design and evaluation are in [STOA_DESIGN.md](STOA_DESIGN.md).
- Stretch goals include handling a differently formatted or scanned schedule with Nemotron, extending evaluation to more projects, and reusing the evidence API in an optional glasses demo.

## Data and validation

Use Stoa’s official preview data and `questions.jsonl`. Esplanades and A-801 have been checked in local data experiments. A second project should be held out to test generalization. Keep source documents and derived assets subject to the license listed for each dataset. [Stoa datasets and sample questions](https://hackjunction.app/participate/45/challenges/335)

Ask the Stoa mentors which question families they will try live and whether a scoped prototype covering native IFC and door schedule PDFs matches their expectations.

## Submission checklist

Final submission is due Sunday, November 15, at 10:00 Helsinki time. [Official schedule](https://hackjunction.app/hackathons/junction-2026)

- [ ] Complete the live demo and record a pitch video within the two-minute limit.
- [ ] Add the demo URL, source link, description, and pitch materials to Junction.
- [ ] Run a held-out comparison and state which inputs and question families the prototype supports.
- [ ] Select technical awards whose integrations can be shown and explained in the submission.

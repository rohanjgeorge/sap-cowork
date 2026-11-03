# Formatted artifact viewer

The generated BRD was correctly stored as structured Markdown, but the workspace rendered it with the basic CommonMark parser. Tables are a GitHub-Flavored Markdown extension, so pipe-delimited document information and history tables appeared as source text in the browser even though the Word export rendered tables.

The artifact viewer now enables `remark-gfm` alongside the existing React Markdown renderer. Tables render as semantic rows/cells with borders, shaded headers and readable cell padding. The document surface uses a paper-style layout, Calibri/system fallback typography, clear headings, paragraph/list spacing and inline-code styling. Wide tables scroll inside a keyboard-focusable labelled region on small screens. ABAP remains literal source code. Raw HTML execution is not enabled.

This is a Word-style HTML presentation of the existing artifact content. It does not embed Microsoft Word or promise identical pagination/font metrics across browser and Word. The existing Word download remains available. Stored artifact content, versions, approvals, source references, generation and editing contracts are unchanged; viewing does not regenerate or rewrite documents.

Files changed: `frontend/src/Files.tsx`, `frontend/src/styles.css`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/src/Files.test.tsx`, `frontend/e2e/experience.spec.ts`.

Verification: a new UI case reproduced the missing table before the fix; the existing heading remained correctly rendered while no column-header cells existed. New checks cover table cells, bold/list/code rendering, the original editable source, and literal ABAP. The browser regression checks metadata-table display, header shading, desktop/mobile layout, local horizontal scrolling and preservation of stored content. Its fixture compares against the post-edit lifecycle-normalized source because the existing backend correctly updates Version History on editing.

The focused browser scenario passed, the UI suite passed 40 tests, and the production build passed. Desktop and mobile screenshots were inspected. Complete release evidence is in `TEST_RESULTS.json`, with the STO business scenario executed last. No paid model calls or changes to user project artifacts were needed.

References: [remark-gfm](https://github.com/remarkjs/remark-gfm) and [React Markdown](https://github.com/remarkjs/react-markdown).

Final release result (2026-11-03T08:02:44.448556+00:00): 235 backend/CLI tests, 40 UI tests, 11 browser experience tests, and the final STO scenario passed. Lint, formatting, production build and dependency audit passed (0 vulnerabilities). Seven existing non-failing LangGraph durability warnings remain. The local server was verified to serve the rebuilt bundle containing the formatted table renderer, so a browser refresh is sufficient. No commit or push was performed.

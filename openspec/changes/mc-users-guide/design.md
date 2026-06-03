## Context

pqwave has an extensive Monte Carlo analysis feature set but no user-facing documentation. The Help menu currently has no entries specific to MC workflows. Users must discover features by exploring menus and dialogs.

Existing artifacts:
- `docs/monte_carlo/` already exists with example files and a raw ngspice reference page
- `pqwave/ui/menu_manager.py` builds menus programmatically with `callbacks` dict
- `pqwave/ui/main_window.py` wires callbacks for all menu actions
- The Help menu currently has no sub-items beyond About

## Goals / Non-Goals

**Goals:**
- Write `docs/monte_carlo/guide.md` covering all MC features end-to-end
- Add "Monte Carlo Guide" action to Help menu that opens the guide in a dialog
- Guide renders as Markdown in a read-only text viewer (QTextBrowser)

**Non-Goals:**
- In-app interactive tutorial or wizard
- Video content or animated demos
- Translated versions
- Modifying any MC feature behavior

## Decisions

1. **Format: Markdown rendered in QTextBrowser**
   - QTextBrowser handles basic Markdown (headings, lists, code blocks) natively
   - No external dependency needed
   - Alternative considered: opening external browser to a local HTML file → rejected because offline help should work without a browser

2. **Menu placement: Help menu**
   - The Help menu is the standard location for documentation
   - Alternative considered: Analyze menu → rejected because user guides are not analysis tools

3. **Guide location: `docs/monte_carlo/guide.md`**
   - Co-locates with existing MC example files
   - Alternative considered: `docs/` root → rejected because it would pollute the root without context

4. **Guide structure: Workflow-based (load → explore → analyze → generate → script)**
   - Sections 1–4 follow the natural GUI user journey
   - Section 5 covers the session API / headless scripting interface
   - Each section is self-contained so users can jump to what they need
   - Includes concrete examples referencing the example files already in `docs/monte_carlo/examples/`

## Risks / Trade-offs

- **Guide may drift from implementation** → Link to specific UI labels and menu paths so drift is easy to detect; include a version note at the top
- **Large single file** → Split into `##` sections with a table of contents; keep under 800 lines

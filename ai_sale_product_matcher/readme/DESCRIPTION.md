Find best-matched PIM products from requirement documents/images using a vision LLM.

Upload a spec sheet, email screenshot or type requirements (e.g. "120 bar soğuk sulu,
monofaze, 2.3kW, deterjan tanklı") — the module extracts a canonical requirements JSON
using the same `ai_connection` `openai_compatible` vision pipeline as
`ai_document_extraction` (only prompts differ), then scores all `product.template`
records against the PIM attribute catalog (`katalog-sablonu.json` → 232 keys) with
type-aware matching (range, tolerance, fuzzy) and weighted groups. Top 10 matches are
shown on the Sales order with match % and can be added as order lines.

Sales (Satış) integration: `sale.order` → _Find Products with AI_ wizard (file + text →
Extract → editable JSON → Find Matches → Add to Order). Extraction runs via
`queue_job` + `bus` so UI never blocks.

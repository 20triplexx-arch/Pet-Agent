disposition: ship — scoped extension documentation

# Deep chat documentation record

Recorded: 2026-10-12. This is an ordinary extension of the approved soft-white/berry world. Operate governs the question, supplemental context and explicit actions; Read governs assistant answers. The shipped code, incumbent `DESIGN.md` and `deep-chat-review.md` supply authority. No new world, seed, assets or primary navigation were introduced.

## Preservation

`DESIGN.md` and `.impeccable/design.json` remain untouched. Their confirmed palette, local Noto Sans SC, Phosphor icons, flat surfaces, control shapes and five mobile navigation entries continue to apply. The existing `.impeccable/surfaces/deep-chat.md` already describes this extension accurately and also remains untouched. Rules below belong to the deep-chat surface; they do not replace global tokens or promote its layout into a rule for other pages.

The parent reported pre-existing date/buildPath drift in the incumbent design artifacts. The sidecar still carries `generatedAt: 2026-10-11T08:00:48.911Z`. This pass records that drift without refreshing metadata, rewriting the sidecar, or treating its repair as a prerequisite to shipping this extension.

## Incremental rules grounded in the implementation

| Rule | Shipped behavior | Source |
| --- | --- | --- |
| Keep the composer available | The chat panel is a bounded vertical flex container. Messages have `overflow-y: auto`, `flex: 1` and `min-height: 0`; toolbar and composer sit outside that scroller. Deep-chat panel height is `100dvh - 180px` on desktop and `100dvh - 280px` below 768px, with existing minimum heights of 420px and 410px. | `frontend/src/styles.css`, `frontend/src/pages.tsx` |
| Keep depth beside the question | Automatic, brief and detailed choices, the supplement trigger and the `12000` limit stay in the composer. Oversized input remains visible, produces “请分次发送,” and disables submission rather than silently truncating it. | `frontend/src/pages.tsx` |
| Separate reading hierarchy from controls | Assistant prose remains 16px with 1.9 line height and a maximum width of 72ch. Major answer headings are 20px/1.5, 19px on mobile; subheadings are 17px/1.6. Paragraphs, lists and small inline emphasis provide structure without additional panel layers. | `frontend/src/styles.css`, `frontend/src/answer-content.tsx` |
| Contain wide evidence | Comparison tables retain columns within a named, keyboard-focusable horizontal scrolling region. Tables use 14px text, tabular numerals, left-aligned cells, fine bottom borders and an incumbent pale-berry header. Local table scrolling must not become document overflow. | `frontend/src/answer-content.tsx`, `frontend/src/styles.css` |
| Cite known chapters | Inline citations resolve only against the answer's source IDs and supplied section names. Source disclosures retain original professional links and real knowledge chapter links. React escapes text; the answer renderer supports a small Markdown subset and does not render raw HTML or arbitrary remote Markdown links. | `frontend/src/answer-content.tsx`, `frontend/src/components.tsx`, `frontend/src/api.ts` |
| Keep extra facts optional and attributed | Six labeled fields cover goal, observations, timeline, diet/activity, environmental changes and user-provided professional advice. Time and source guidance, unknown values and session-only wording stay visible. Their existing white fields, fine boundaries and 14px labels remain subordinate to the question. | `frontend/src/chat-supplement.tsx`, `frontend/src/styles.css` |
| Reveal nutrition only when needed | Optional nutrition uses the existing validation contract, unknown defaults and explicit confirmations. This compact disclosure supports one main food; mixed foods and treats point to the full nutrition page. Editing a new food resets food-list confirmations. User-entered professional advice is not presented as independently verified advice. | `frontend/src/chat-supplement.tsx`, `docs/DEEP_CHAT.md` |
| Preserve return paths across devices | Supplement stays in the desktop context column and follows chat in the single-column layout. Opening it scrolls to the disclosure; “回到提问” closes it and focuses the question. The disclosure retains native interaction and visible focus. | `frontend/src/pages.tsx`, `frontend/src/styles.css` |
| Keep answer actions deliberate | Copy updates its own label; a clipboard failure offers manual selection in a status message. “继续深入” fills an unsent detailed follow-up and focuses the composer. It does not submit a new request automatically. | `frontend/src/pages.tsx` |
| Protect reading position | The existing message list positions a newly opened history or a followed reply at the latest message's beginning. Reading older content preserves the user's position and exposes “查看最新回复” when appropriate. | `frontend/src/pages.tsx` |
| Put urgency and write boundaries in words | “紧急就医提示” appears before urgent assistant content. Hospital and nutrition links remain explicit actions. Drafts retain “尚未保存” and “预览 / 编辑后保存.” Supplement fields state that pet profiles, records and feeding tasks do not change automatically. | `frontend/src/pages.tsx`, `frontend/src/chat-supplement.tsx` |
| Scope unsent context to its conversation | Switching history or creating a conversation clears the unsent supplemental object. Switching pets remounts the keyed main workspace and clears unsent chat state. Previously sent facts can remain in their own conversation with provenance; blank input is not a deletion control. | `frontend/src/pages.tsx`, `frontend/src/App.tsx`, `docs/DEEP_CHAT.md` |
| Keep demonstration truth visible | Assistant mode labels distinguish demonstration, model answers and tools. Existing context copy states how the demonstration works. The documentation must not turn synthetic local-calculation output into a claim of real model or clinical quality. | `frontend/src/pages.tsx`, `docs/DEEP_CHAT.md` |

## Evidence and limits

The accepted review has `disposition: ship` and no material fixes. It checked the six required answer/supplement/table desktop and mobile PNGs and the one detector result, `deep-chat-detect.json` (`[]`). Full-page captures begin at document top; table PNGs are explicit element crops. A fixed navigation bar's position in a stitched full-page capture and the mobile table's partially visible last column at initial scroll are capture/scroll-region behavior, not new layout rules or defects to legitimize.

The parent reports a successful frontend build, 158 backend tests and all 60 desktop/mobile Playwright tests. This documenter did not rerun the detector, browser, build or tests. Source inspection confirms the mechanisms above. The initial answer captures do not show controls farther down the internal scroller; chapter sources, Copy and Continue deeper are therefore supported here by source inspection and the accepted review, not by an invented screenshot claim. No real model key was used, so provider reasoning quality, latency, cost and clinical correctness remain outside this evidence.

Checked: `DESIGN.md`, `.impeccable/design.json`, `.impeccable/surfaces/deep-chat.md`, `.impeccable/review/deep-chat-review.md`, `PRODUCT.md`, `docs/DEEP_CHAT.md`, `frontend/src/styles.css`, `pages.tsx`, `components.tsx`, `answer-content.tsx`, `chat-supplement.tsx`, `api.ts`, and the keyed chat workspace in `App.tsx`.

## Not canonized or repaired

No new craft-floor defect is recorded as house style. The incumbent date/buildPath drift is preserved because refreshing global design artifacts is outside this ordinary extension. The surface's answer measure, table region, composer heights and supplement behavior remain local rules, not replacements for the global system.

# X18 UI redesign: research and palette

## Sources (minimalist "type text, get a result" interfaces)
1. Perplexity: NN/g interview with its design lead, https://www.nngroup.com/articles/perplexity-henry-modisett/ . The input looks and feels like a familiar search box. The answer is direct, not a conversation, and sources sit right with the answer.
2. Perplexity design study, https://blakecrosley.com/guides/design/perplexity (a third-party reconstruction, values approximate). Neutral base with one accent used only for citations, focus and hover. Radii of 8-12px on cards and pill shapes for status. Answer column capped near 680px. Cards fade in and rise about 8px over 0.3s. System font stack with a small type scale.
3. Google Search mobile redesign, https://blog.google/products-and-platforms/products/search/mobile-redesign-2021/ . Larger, bolder titles. Fewer shadows. Colour used sparingly on a clean background. Rounded shapes borrowed from the logo.
4. Linear UI redesign, https://linear.app/blog/how-we-redesigned-the-linear-ui . The theme comes from three inputs (base, accent, contrast) instead of 98 variables. The accent is limited "for a more neutral and timeless appearance". Elevation comes from small lightness steps, and text is darker in light mode and lighter in dark mode for readability.
5. DeepL Pro redesign, https://www.deepl.com/en/blog/new-pro-experience , and Red Dot profile, https://staging124.red-dot.org/ko/project/deepl-41313 . The workspace was cleared to keep users focused on the one task, following "form follows function".
6. Minimalist search UX, https://vectree.io/c/search-interface-cognitive-ux . Whitespace is functional: it guides the eye to the search bar and the results.

## Patterns that recur, and what was adopted
- **One dominant input.** The Check page's claim box is now a large rounded composer (24px radius, soft shadow), centred under a big heading. The Break down button sits inside it as a pill. After submission it collapses into a quiet grey summary of the claim. Abstracts search uses the same pill-shaped input-plus-button pattern.
- **Generous whitespace and a narrow column.** Content is capped at 56rem, the abstract text at 42rem, and the spacing scale is 4/8/12/16/24/32/48px.
- **Restrained type.** One system font stack (monospace only for JSON and prompts). Six sizes: 12, 14, 16, 18, 24 and 32px. Uppercase micro-labels for table headers and section labels.
- **Neutral base, one accent.** A warm off-white or near-black base, with indigo used only for primary actions, links, the active nav pill, focus rings and the trace dots. Verdict colours appear only on verdict badges and quote bars.
- **Soft radii, one scale.** 6px (small focus targets), 12px (inputs, buttons, quotes, callouts), 18px (cards, tables), 24px (composer, dialog), and full pills for badges, tags, nav links, the progress chip and search.
- **Subtle elevation.** Three shadow tokens (sm, md and lg). Dark mode leans on lighter surfaces plus heavier, softer shadows.
- **Gentle motion.** 150/200/260ms on a smooth ease-out (cubic-bezier .2,.8,.2,1) for hover, focus and colour. Results, review, callouts, the trace rows and doc cards fade and rise 6px, with statement cards staggered 60ms. Under `prefers-reduced-motion` all of this is cut to 1ms and the spinner slows down.
- **Visible focus.** A 2px accent outline (`:focus-visible`). Inputs and the composer get an accent border plus a soft 3-4px accent halo.
- **Phone width.** At 640px and narrower, the statements, traces and review-score tables become stacked rows. Labels come from CSS `::before`, so the markup is unchanged. The trace Expand button is pinned to the top right. Playwright measured no horizontal overflow at 375px on any screen.

## Palette: "Paper & Indigo"
Defined once in `web/src/styles.css` on `:root`, with the dark set under `@media (prefers-color-scheme: dark)`. A grep of styles.css outside those two blocks finds 0 colour literals, and the TSX/TS files contain no colour literals or inline styles.

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| --bg | #f6f6f3 | #121316 | page |
| --surface | #ffffff | #1b1c20 | cards, inputs |
| --surface-2 | #efefeb | #24262b | quotes, code, sunken areas |
| --text | #1d1e22 | #e9e9ec | body text |
| --muted | #5d616b | #a0a4ae | secondary text |
| --border | #e2e2dc | #2f3138 | hairlines |
| --accent | #4b46d8 | #9b98ff | primary actions, links, focus |
| --on-accent | #ffffff | #121316 | text on accent |
| --accent-soft | #ecebfc | #262546 | active nav, info callout, halos |
| --supported / -soft | #17723a / #e4f3e9 | #64d08c / #16291d | supported verdict |
| --contradicted / -soft | #b42323 / #fbe8e6 | #ff8b80 / #3a1c1a | contradicted verdict, errors |
| --unknown / -soft | #565c66 / #ececef | #b0b5bf / #2a2c31 | unknown verdict |
| --warning / -soft | #8f5300 / #fcf0da | #f2b860 / #33270f | needs-attention and consistency callouts |

Scrim and shadow tokens are translucent tints of --text (light) or black (dark).

### WCAG contrast (computed with the WCAG 2.x relative-luminance formula; AA needs 4.5:1)
| Pair | Light | Dark |
| --- | --- | --- |
| text on bg | 15.38 | 15.33 |
| text on surface | 16.65 | 14.05 |
| text on surface-2 | 14.45 | 12.49 |
| muted on bg | 5.73 | 7.44 |
| muted on surface | 6.20 | 6.82 |
| muted on surface-2 | 5.38 | 6.07 |
| accent on bg | 6.12 | 7.37 |
| accent on surface | 6.63 | 6.75 |
| on-accent on accent | 6.63 | 7.37 |
| accent on accent-soft | 5.64 | 5.80 |
| supported on supported-soft | 5.22 | 7.99 |
| contradicted on contradicted-soft | 5.55 | 6.80 |
| unknown on unknown-soft | 5.71 | 6.79 |
| warning on warning-soft | 5.47 | 8.21 |
| text on warning-soft | 14.76 | 12.05 |
| contradicted on surface | 6.55 | 7.50 |

Every pair passes AA for normal text.

## Screenshots
`shots/` holds the screens at 1280px and 375px wide, in light and dark: `<width>-<scheme>-NN-<screen>.png`. The screens are the empty Check page, a typed claim, the access code dialog, the statements review, verifying, the result, the Traces list, a trace timeline with one span expanded, Abstracts search, and an abstract detail. Every `/api/*` call was mocked with `page.route`; no models or live site were called. The script is `scratchpad/e2e/x18-shots.mjs`.

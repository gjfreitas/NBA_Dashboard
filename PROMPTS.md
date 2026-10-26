# Prompts to run on this app

Audit prompts for the frontend, adapted from the "designers: prompts to run on your application" idea. Run one after any large UI change, or before a release. Each says when to run it and what a good result looks like. Paste the prompt into Claude Code from the repo root.

## 1. Accessibility (axe)

**Run:** after adding or restyling pages, and after any colour change (check both themes).

```
Run axe-core (wcag2a, wcag2aa, wcag21aa, best-practice) against every route in
frontend/app, in both prefers-color-scheme values, at desktop and 375px width.
Use a real game id and player id from the running API. Group violations by rule,
fix each at its source component, and re-run until the list is empty. Report
anything axe cannot judge (focus order, motion) separately and check it by hand.
```

**Good result:** zero violations on every route in both themes; heading levels never skip (one `h1` per page); icon-only buttons have names; status text is announced once, not per clock tick. Colour contrast is only checked when the page is visible (not `opacity: 0`).

## 2. UX friction

**Run:** after adding a filter, a search, or any view that depends on data that may be missing.

```
Read frontend/components and app and list, with file:line, every place where:
a search or filter can return nothing without saying so; a request can fail
silently or spin forever; a control gives no feedback; a first-time visitor sees
developer wording (commands, table names); a tap target is under 44px; a screen is a
dead end. Rank by visitor impact, quote the line, propose the smallest fix. Then fix
the top items.
```

**Good result:** every empty state says what is missing and what to do next, in plain words; every error has a retry or a way back; nothing tells a visitor to run a command (that stays in small print for the site owner).

## 3. Performance

**Run:** after adding polling, a new data panel, or an animation.

```
Audit loading performance: components that poll (interval, hidden-tab behaviour,
duplicate endpoints), payload sizes from the API with curl, work done in render on
large lists, animations on non-compositor properties or on many elements,
fixed/sticky layers with blur, unused dependencies, images without size.
Quantify, rank by visible impact, fix the top items, and re-measure.
```

**Good result:** one request per endpoint per interval no matter how many components read it; no polling while the tab is hidden; large optional tables fetched less often than the visible content; only `transform` and `opacity` animate on lists.

## 4. Visual consistency

**Run:** after touching `globals.css` tokens or adding a component.

```
Screenshot every route at 375px and 1280px in dark and light. List anything that
looks unfinished: text clipped or overlapping, uneven spacing, a colour that is not a
token, a heading that does not use the display font, a card without the shared style,
an element that jumps when data arrives. Fix at the token or shared component, not
per page.
```

**Good result:** no raw hex in components; skeletons match the final layout height so nothing shifts when data loads; team colours come only from `lib/teamColors.ts`.

## 5. Motion

**Run:** after adding any animation.

```
List every animation and transition. For each: what does it tell the user, which
properties does it animate, how long, and is it off under prefers-reduced-motion?
Remove any that only decorate or that animate layout properties.
```

**Good result:** each motion explains a change (a score updating, a tab moving, a row arriving); durations under 400 ms except ambient loops; reduced motion shows the final state with no movement.

## Tooling

axe-core is a dev dependency (`npm i -D axe-core`). To run it inside the dev server, copy `node_modules/axe-core/axe.min.js` into `frontend/public/` for the session, load it in an iframe per route, and delete the copy afterwards (it breaks `npm run lint`).

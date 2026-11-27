---
name: web-frontend
detect:
  files: ["**/*.tsx", "**/*.jsx", "**/*.vue", "**/*.svelte", "**/*.component.ts", "**/vite.config.*", "**/next.config.*", "**/angular.json"]
  weak: ["**/*.ts", "**/*.js", "**/*.mjs", "**/package.json", "**/*.css", "**/*.scss", "**/*.html"]   # count only when a files glob or signal also matches
  signals: ["react", "vue", "svelte", "@angular", "antd", "@tanstack/react-query", "jotai", "redux"]
evidence: code review findings on React/TypeScript UIs; the framework-neutral parts apply to Vue, Svelte and Angular
---

# Web frontend (React, Vue, Svelte, Angular)

## Build

- **Use what the repo uses.** Follow the framework and UI library the profile detects. Don't add a second state, data or UI library.
- **TypeScript:**
  - strict mode, with no `any`;
  - explicit prop types;
  - `import type`;
  - `readonly` where values shouldn't change.
- **Components:**
  - small components (about 100 lines);
  - custom hooks for reusable logic;
  - composition over prop drilling: past 2–3 levels, use context or composition.
- **State:**
  - local: `useState`;
  - global client state: the repo's store (Jotai atoms, Redux, Zustand, Pinia);
  - server state: the repo's data layer. With TanStack Query, every input goes into the query key, and mutations invalidate every affected key.
- **API:**
  - one client module per backend (an axios or fetch wrapper with auth, and the base URL from env);
  - validate responses where the repo does (zod).
- **UI library:** use its components and theme, for example Ant Design `Form`, `Table` and `Modal` when `antd` is detected, and keep its built-in accessibility.
- **UI states:** loading, error and empty are distinct. Permission-gated UI fails closed.
- **Performance:**
  - route-level code splitting (`React.lazy`, dynamic `import()`);
  - memoize expensive computations;
  - no inline object props on memoized children;
  - virtualize long lists.
- **Accessibility (WCAG 2.1 AA):**
  - semantic elements (`<button>` for actions, `<a>` for navigation);
  - a label for every input;
  - headings in order, and landmarks;
  - everything reachable by keyboard with a visible focus, Escape closes overlays, and no traps;
  - alt text, and contrast of at least 4.5:1;
  - errors announced (`aria-live`, `role="alert"`) and linked to their fields (`aria-describedby`);
  - never color alone.
- **Env:** only public-prefixed variables (`VITE_`, `NEXT_PUBLIC_`) reach the client, and never secrets.

## Review

### How the failure modes show up
- **FM-03 Irreversible:** an idempotency or request id regenerated when a modal reopens or a submit is retried, which allows a double buy or post.
- **FM-05 Loops:** polling or WebSocket reconnects without gating or backoff; backoff reset on open, causing tight loops.
- **FM-07 Concurrency:** debounced search races; out-of-order responses overwrite newer ones; a closed modal or unmounted component keeps applying results (missing abort or `isCurrent` check).
- **FM-11 Semantics:**
  - logic keyed on labels or backend message text;
  - event times shown in browser time instead of the event's timezone;
  - date-only values shifting a day through `new Date()`;
  - client caps (200–10,000 rows, page limits) silently truncating filters, totals and exports.
- **FM-12 Caching:**
  - query keys missing a filter input;
  - mutations that don't invalidate every query they affect;
  - a refetch that wipes unsaved form input;
  - a row snapshot held in a drawer that goes stale after refresh.
- **FM-13 Authz:**
  - client role lists out of step with the server (a role silently loses access, or an action is offered that returns 403);
  - roles not taken from one shared constant;
  - a client-only lock is never enforcement.
- **FM-14 Secrets:**
  - card data, passwords or tokens in `console.log`, URLs, WebSocket query strings, CSV exports or over-fetched rows;
  - `VITE_`/`NEXT_PUBLIC_` vars holding secrets.
- **FM-15 Config:** a build-time env var read in code but not set in deployed env files, so the feature silently disappears in staging or prod.
- **FM-16 Perf:** per-keystroke fan-out without debounce; re-fetching thousands of rows on an interval; large lists without virtualization.
- **FM-17 User-facing truth:** every rule in the generic family. It is the largest frontend bucket.

### Stack-only checks
- **Stable list keys.** List keys must be stable, not array indexes, when items are added, removed or reordered.
- **Effect dependencies.** Effects must declare complete dependencies; missing deps leave stale closures, extra deps cause refetch loops.
- **Unsafe HTML.** `dangerouslySetInnerHTML`/`v-html` only with sanitized content.
- **CSV export formula guard.** Cells starting with `=`, `+`, `-`, `@` or a tab get escaped.
- **Backend first.** A change that needs a backend change states the dependency and ships after it.
- **Accessibility regressions.** Watch for:
  - removed labels;
  - a clickable `div` instead of a `<button>`;
  - focus lost or trapped when a modal opens or closes;
  - an icon-only button with no accessible name;
  - color as the only signal.

  These are `consider` by default, and `important` when they block a user flow for keyboard or screen-reader users.

## Test

- **Tools:** Vitest or Jest with Testing Library (query by role or label, `user-event`) and MSW for API mocks; Playwright or Cypress for e2e where present.
- **Test behavior, not implementation:** render, interact, and assert what the user sees. Cover loading, error and empty states, and permission-gated rendering.
- **Hooks and stores:** hooks through `renderHook`; reset stores between tests.
- **Accessibility:**
  - run jest-axe or axe-core checks where the repo uses them;
  - test keyboard-only flows for modals and forms.

## Commands

- **Scripts:** dev, build, test, lint and typecheck come from `package.json` scripts. Default dev ports are Vite 5173, Next 3000 and Angular 4200. The typecheck fallback is `tsc --noEmit` (inferred).
- **E2E:** suites (Playwright, Cypress) run only when the user confirms, since they start browsers and may need a backend.

## Entry points (scan mode)
- The router config;
- pages and routes;
- API client modules;
- auth guards and role constants;
- env files (`.env*`) and build config.

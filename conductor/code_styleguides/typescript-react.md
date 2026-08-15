# TypeScript / React Style Guide — Narrative Intelligence Engine

Incorporates the existing `frontend/.oxlintrc.json` configuration —
enforce what it enforces, and follow the conventions already visible in
`frontend/src/`.

## Enforced by existing tooling (`oxlint`)

- `react/rules-of-hooks`: error — never call hooks conditionally or
  outside component/hook bodies.
- `react/only-export-components`: warn, with `allowConstantExport: true`
  — component files should primarily export components; constant exports
  alongside them are fine.
- Plugins active: `react`, `typescript`, `oxc`. Run `npm run lint`
  (`oxlint`) before committing frontend changes.

## Observed conventions (keep following these)

- Functional components with TypeScript, no class components.
- Data fetching via `@tanstack/react-query` — see `frontend/src/lib/api.ts`
  for the fetch wrappers and `frontend/src/lib/queries.ts` for query hook
  definitions. New data needs should follow this pattern: a typed fetch
  function in `api.ts`, a `useQuery`/`useMutation` hook in `queries.ts`,
  consumed from a page/component — not ad-hoc `fetch()` calls inside
  components.
- Types for API/domain data centralized in `frontend/src/types/state.ts`.
- Directory structure by concern: `components/{graph,ingest,layout,
  reports,state,ui}/`, `pages/`, `lib/`. Place new components in the
  matching subdirectory rather than flattening into `components/`.
- Styling via Tailwind CSS 4.x utility classes; `clsx` + `tailwind-merge`
  for conditional/merged class names — avoid separate CSS-module files
  for one-off component styling.
- Radix UI primitives for accessible interactive components (dialog,
  dropdown, tabs, tooltip, switch, accordion, progress) — prefer wrapping
  a Radix primitive over hand-rolling accessibility behavior.
- `sonner` for toast/notification UI, `framer-motion` for animation,
  `lucide-react` for icons — reuse these rather than adding alternative
  libraries for the same purpose.

## Build & verify

- `npm run dev` — Vite dev server
- `npm run build` — `tsc -b && vite build` (type-checks as part of build)
- `npm run lint` — `oxlint`
- Manually exercise changed UI in the dev server before considering a
  frontend phase done, per [[workflow]]'s verification-checkpoint policy.

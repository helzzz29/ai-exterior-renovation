# Home Makeover Planner

A pre-construction planning assistant for house exteriors. A homeowner uploads one photo of the front of their house, checks the parts the system found, picks materials, sees their own house redesigned, and gets a transparent quantity and cost estimate as a PDF report to discuss with contractors.

## Credits and changes

This project is built on a codebase shared by a friend ([Jainam2806/renovation](https://github.com/Jainam2806/renovation)), used with their permission. Changes made on top of it:

- Frontend: new dashboard shell with a sidebar, dark theme, project stats and search, and a tab-style step navigation.
- Local setup fixes (pnpm build approvals, seed script for test accounts).

## How it works

| Step | What happens | Who does it |
|---|---|---|
| Photo check | Format, sharpness, exposure; "is this a house exterior, taken straight on?" | Code + **Jev** |
| Find the parts | The photo is repainted as a colour-coded map (walls, windows, doors, pillars, balconies, parapets, railings, gates, roof edges), then turned into editable outlines | **Gemini** image model + code |
| Label and double-check parts | Each part is confirmed from a close-up; unsure ones are marked *Please check* | **Jev** |
| Size reference | Main door box and floor count, or a measurement from the homeowner | **Jev** + code |
| Material suggestions | Recommended / not-ideal materials per type of surface | **Jev** |
| New look | Photoreal redesign blended back only inside the chosen parts, then checked for changed windows/doors or missing materials (auto-redo up to 2×) | **Gemini** + code + **Jev** |
| Quantities and costs | Area, wastage, coats, packs, material and labour, scaffolding, contingency, GST, range | Code only |
| Report | Before/after, materials, derivations, costs, assumptions, accuracy notes | Code (ReportLab) |

Models look and draw; deterministic code measures and calculates. Measured live: analysis ≈ 25 s, a new look 40 s – 2.5 min depending on automatic re-checks.

## Stack

FastAPI · Pydantic · SQLAlchemy + Alembic · PostgreSQL · Procrastinate (Postgres job queue) · Pillow / OpenCV / Shapely · ReportLab · `google-genai` · `typesafe-sdk` · React 19 + Vite + TypeScript · Tailwind + shadcn/ui · react-konva · TanStack Query.

## Run it locally

Requirements: Docker, [uv](https://docs.astral.sh/uv/), Node 20+ and pnpm. Two API keys: Gemini (with image generation enabled, i.e. a billing-enabled project) and TypeSafe Jev.

```bash
cp .env.example .env            # fill in GEMINI_API_KEY and JEV_API_KEY
docker compose -f infra/docker-compose.yml up -d --wait   # Postgres (dev :5433, test :5434)

cd apps/api
uv sync
uv run alembic upgrade head
uv run python -m renocore.server       # API on http://localhost:8000
uv run python -m renocore.background.runner   # in a second terminal: background jobs

cd ../web
pnpm install
pnpm dev                        # app on http://localhost:5173
```

`pnpm dev:mock` runs the whole journey in the browser with a mock API and no keys (demo login `demo@example.com` / `password123`).

Sample photos with attributions are in [`samples/`](samples/).

## Deploy

One container (website + API + job worker) on Render's free plan, with Neon Postgres for data and a private Backblaze B2 bucket for images. No card needed for any of them. `docker build -t renovation-planner .` builds the same image locally.

## Tests

```bash
cd apps/api && uv run pytest -q          # unit + integration (needs the test database)
cd apps/api && uv run ruff check app tests
cd apps/web && pnpm test && pnpm typecheck && pnpm lint
```

Normal tests never call Gemini or Jev; a fake provider stands in. Live checks are opt-in: `RUN_LIVE=1 uv run pytest -m live tests/live`.

## Repository layout

```
apps/api     FastAPI app, worker, estimation engine, imaging, AI integration, PDF report
apps/web     React app (and an in-browser mock API)
seed         material catalogue and swatches
samples      openly licensed sample photos
infra        docker compose (Postgres)
```

Estimates are advisory planning figures, not quotations.

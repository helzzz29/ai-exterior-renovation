# Renova AI — Exterior Home Makeover & Cost Estimation Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19.1+-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-v4-38B2AC?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> **Renova AI** is a full-stack, AI-driven pre-construction planning platform for residential exterior renovation. Homeowners upload a single daylight photo of their house facade, verify and adjust detected architectural boundaries, select modern exterior finishes from an authentic Indian building catalogue, visualize photorealistic redesigns, and receive an itemized Bill of Quantities (BOQ) with a contractor-ready PDF estimate in Indian Rupees (₹).

---

## Table of Contents

- [Problem Statement & Solution](#problem-statement--solution)
- [Key Features](#key-features)
- [How It Works (Pipeline)](#how-it-works-pipeline)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Materials Catalogue](#materials-catalogue)
- [Getting Started Locally](#getting-started-locally)
  - [Prerequisites](#prerequisites)
  - [Environment Configuration](#environment-configuration)
  - [Database Setup](#database-setup)
  - [Running Backend & Worker](#running-backend--worker)
  - [Running Frontend](#running-frontend)
  - [Running in Offline / Mock Mode](#running-in-offline--mock-mode)
- [API Documentation](#api-documentation)
- [Testing & Quality Assurance](#testing--quality-assurance)
- [Repository Layout](#repository-layout)
- [Deployment](#deployment)
- [Authors & Acknowledgments](#authors--acknowledgments)

---

## Problem Statement & Solution

### The Problem
- **Visualization Barrier**: Homeowners struggle to imagine how new exterior finishes (textures, stone claddings, WPC louvers, ACP sheets) will look on their actual home before investing lakhs of rupees.
- **Contractor Quote Discrepancies**: Estimates from local contractors are frequently arbitrary or inflated without transparent area deductions (windows/doors), coat schedules, primer requirements, or scaffolding allowances.
- **Trial-and-Error Expenses**: Reworking poorly planned facade treatments after installation leads to costly delays and aesthetic compromises.

### The Solution: Renova AI
- **Single-Photo Intake**: Uploads a standard front-facing smartphone photo with automated validation (aspect ratio, sharpness, exposure, perspective).
- **Interactive Architectural Geometry**: Automatically identifies facade sections (walls, balconies, windows, doors, chhajjas/canopies, louvers, compound walls) into editable polygon coordinates via HTML5 Canvas.
- **Intelligent Budget Flexibility**: Mark surfaces as *Mandatory* (Main Wall), *Openings* (deducted from surface area), or *Optional* with a **"Keep Existing (Exclude from Budget)"** toggle.
- **Deterministic Estimation Engine**: Calculates exact physical measurements (sqft / rft), material packs, companion requirements (primer/adhesive), wastage buffers, labor rates, scaffolding, contingency, and 18% GST.
- **Photorealistic AI Visualization**: Combines Gemini generative models with boundary masking to produce precise Before/After interactive comparisons.
- **Contractor-Ready PDF Report**: Generates a downloadable, print-ready PDF specification for site meetings and material procurement.

---

## Key Features

### 1. Architectural Section Segmentation & Editing ("Spot the Sections")
- **AI Boundary Detection**: Translates facade photos into clean vector polygons categorized by architectural function.
- **Comprehensive Building Elements**:
  - 🔵 **Mandatory**: Main Wall (`wall`) — the core renovation canvas.
  - ⚪ **Openings (Deducted)**: Windows (`window`) and Doors (`door`) — excluded from painting/cladding areas.
  - 🔘 **Optional Facade Features**: Balconies (`balcony`), Pillars (`pillar`), Parapets (`parapet`), Roof Edges (`roof_edge`), Railings (`railing`), Gates (`gate`), Chhajjas / Canopies (`canopy`), Louvers / CNC Jalis (`louvers`), and Compound / Boundary Walls (`compound_wall`).
- **Interactive Konva Canvas**: Full polygon editing suite supporting point dragging, adding new parts via polygon trace or box presets, corner nudging, and real-time undo.
- **"Keep Existing (Exclude from Budget)" Toggle**: Allows homeowners to retain existing structures (e.g., compound wall or upper balcony) visually on the photo while deducting them to ₹0 in the renovation budget.

### 2. Dual Calibration & Physical Scaling ("Measure Up")
- Converts 2D pixel coordinates into real-world metric/imperial units.
- **Auto-Detection**: Infers baseline scale using standard door heights (7.0 ft) and floor levels.
- **Homeowner Calibration**: Allows entering one known measurement (e.g., total front width or building height) to achieve high precision.

### 3. Dynamic Materials & Finishes Catalogue ("Pick Finishes")
- **22+ Built-in Material Finishes**: Economy & Premium Emulsions, Weatherproof Elastomeric Paints, Textured Finishes (Dryblend, Roller, Rustic Trowel), Claddings (Natural Stone, Brick Slips, Granite Slabs), Tiles (Slate, Ceramic, Vitrified, Terracotta Clay), Panels (ACP, HPL Woodgrain, WPC Louvers, Charcoal Fluted, CNC Geometric Jali), and Railings/Gates (Glass, MS, Stainless Steel).
- **Color Customization**: Dynamic tint selection with live swatches and hex overrides.
- **Companion Logic**: Automatically bundles required primers (litres per sqft) and tile/stone adhesives (kg per sqft).
- **Durability & Upkeep Insights**: Provides expected lifespan (e.g., 10–12 years, 20+ years) and maintenance requirements for each finish.

### 4. Photorealistic AI Makeover ("Makeover Preview")
- Uses Gemini generative imaging restricted strictly to assigned exterior regions.
- High-contrast **Before / Compare / After** slider with smooth pan and zoom controls.
- Re-check verification loop ensures original fenestration (windows, grilles, doors) is faithfully preserved without AI hallucinations.

### 5. Transparent BOQ & Itemized Cost Estimation ("Budget & Summary")
- Complete cost breakdown:
  - **Material Cost**: Unit prices, standard pack sizes (1L, 4L, 10L, 20L; 20kg/25kg bags; 8×4 ft sheets), and wastage allowances (5%–12%).
  - **Labour Cost**: Surface prep, primer application, and finish installation per sqft/rft.
  - **Scaffolding Allowance**: Computed based on facade height and elevation area.
  - **Contingency Buffer**: 10% reserve for unforeseen site repairs.
  - **GST**: Standard 18% tax calculation for construction contracts.
  - **Contractor Price Range**: Low, average, and high estimates reflecting market variance.
- **Custom Price Overrides**: Homeowners can edit individual material and labor rates to match local contractor quotes.

### 6. Architectural PDF Export
- Server-side PDF generation using ReportLab.
- Includes high-resolution project before/after photos, material specification sheets, quantity schedules, detailed derivations, and assumptions notes.

---

## How It Works (Pipeline)

```mermaid
flowchart TD
    A["1. Upload Facade Photo"] --> B["Image Quality Validation (Sharpness, Daylight, Aspect)"]
    B --> C["2. AI Segmentation (Gemini Vision + Geometry Engine)"]
    C --> D["3. Interactive Canvas (Konva Polygon Editor)"]
    D --> E["4. Real-world Scale Calibration (Door anchor or User width)"]
    E --> F["5. Material & Colour Assignment (22+ Indian Catalogue items)"]
    F --> G["6. Photorealistic Redesign (Gemini Guided Inpainting)"]
    G --> H["7. Deterministic Estimation Engine (Area, Packs, Labour, GST)"]
    H --> I["8. PDF Report Generation & Shareable BOQ"]
```

| Step | Operation | Technical Execution |
| :--- | :--- | :--- |
| **1. Photo Intake** | Resolution, sharpness, perspective check | Pillow, OpenCV |
| **2. Detection** | Semantic segmentation into exterior elements | Gemini Vision API + Contour Vectorization |
| **3. Spot Sections** | User boundary inspection and fine-tuning | React-Konva Canvas, Polygon Math |
| **4. Scale** | Pixel-to-foot scale calculation | Geometric bounding box analysis |
| **5. Finishes** | Material selection, tints, companions | Dynamic Catalogue (`seed/materials.json`) |
| **6. Makeover** | Inpainted photorealistic rendering | Gemini Image Generation + Masking |
| **7. Costing** | Material packs, labor, contingency, GST | Deterministic Python Costing Engine |
| **8. Export** | Print-ready PDF report generation | ReportLab, PIL |

---

## System Architecture

```mermaid
graph LR
    subgraph Client ["Frontend (apps/web)"]
        UI["React 19 + Vite"]
        Router["React Router v7"]
        Canvas["Konva Canvas Editor"]
        Query["TanStack Query v5"]
    end

    subgraph Server ["Backend (apps/api)"]
        FastAPI["FastAPI REST API"]
        CostEngine["Deterministic Costing Engine"]
        Alembic["SQLAlchemy 2.0 + Alembic"]
        Worker["Procrastinate Job Runner"]
        PDFGen["ReportLab PDF Generator"]
    end

    subgraph Storage ["Data & Services"]
        DB[("PostgreSQL 16")]
        BlobStore[("Filesystem / B2 Blob Storage")]
        Gemini["Google Gemini AI"]
    end

    UI -->|REST / OpenAPI| FastAPI
    Canvas -->|Polygon Edits| FastAPI
    Query -->|Cached Requests| FastAPI
    FastAPI --> DB
    FastAPI --> CostEngine
    FastAPI --> Worker
    Worker --> Gemini
    Worker --> PDFGen
    Worker --> BlobStore
```

---

## Technology Stack

### Frontend (`apps/web`)
- **Framework**: React 19, TypeScript, Vite
- **Styling**: Tailwind CSS v4, Lucide React icons
- **UI Components**: Radix UI primitives, shadcn/ui patterns
- **Canvas Interaction**: `react-konva`, `konva` (HTML5 canvas polygon drawing and manipulation)
- **Comparisons**: `react-compare-slider` (interactive Before/After reveals)
- **Data Fetching**: `@tanstack/react-query` v5, `openapi-fetch`

### Backend (`apps/api`)
- **Framework**: Python 3.12, FastAPI, Pydantic v2
- **Database & ORM**: PostgreSQL 16, SQLAlchemy 2.0 (asyncio), Alembic migrations
- **Task Queue**: Procrastinate (PostgreSQL-backed asynchronous job worker)
- **Geometry & Vision**: OpenCV, Shapely, Pillow (PIL), NumPy
- **Generative AI**: `google-genai` (Gemini image generation & multimodal reasoning)
- **PDF Generation**: ReportLab
- **Package Manager**: Astral `uv`

---

## Materials Catalogue

Renova AI includes 22 authentic Indian exterior architectural finishes defined in [`seed/materials.json`](file:///Users/salesteam/Projects/AI-Renovation/seed/materials.json):

1. **Exterior Paints**:
   - Economy Exterior Emulsion (₹240/L, 2 coats, with primer)
   - Premium Exterior Emulsion (₹420/L, 2 coats, antifungal)
   - Weatherproof Elastomeric Paint (₹650/L, crack-bridging)
2. **Textured Plasters**:
   - Textured Wall Finish / Dryblend (₹38/kg, cementitious texture)
   - Roller Texture Paint (₹85/kg, soft rolled pattern)
   - Rustic Trowel Plaster Finish (₹48/kg, heavy sand-faced grain)
3. **Natural Stone & Brick Cladding**:
   - Natural Stone Cladding (₹110/sqft, split face stone)
   - Brick Cladding / Brick Slips (₹95/sqft, exposed clay brick slips)
   - Natural Granite Stone Cladding (₹180/sqft, polished/flamed Sadarahalli/Black Pearl)
4. **Wall Tiles**:
   - Slate Stone Wall Tiles (₹140/piece, 1×2 ft)
   - Ceramic Exterior Wall Tiles (₹85/piece, 1×1 ft)
   - Vitrified Exterior Wall Tiles (₹220/piece, 2×2 ft)
   - Terracotta Clay Wall Tiles (₹125/sqft, natural thermal cooling)
5. **Architectural Elevation Panels**:
   - Aluminium Composite Panels / ACP (₹3,400/sheet, 8×4 ft)
   - Exterior Laminate Panels / HPL (₹6,800/sheet, 8×4 ft woodgrain)
   - Wood-look Louvers / WPC (₹780/sheet, 9.5×0.5 ft fluted slats)
   - Fluted Exterior Wall Panels (₹4,200/sheet, 8×4 ft charcoal composite)
   - CNC Geometric Jali Panels (₹3,900/sheet, 8×4 ft laser-cut lattice)
6. **Balcony Railings & Gates**:
   - Toughened Glass Railing (₹1,200/rft, SS fittings)
   - Mild Steel Painted Railing (₹450/rft)
   - Stainless Steel Railing (₹850/rft, Grade 304)
   - Fabricated Mild Steel Gate (₹6,500/rft)

---

## Getting Started Locally

### Prerequisites
- **Node.js**: `v20.18+` or `v22+`
- **pnpm**: `v9+` (`corepack enable && corepack prepare pnpm@latest --activate`)
- **Python**: `3.12+` with [`uv`](https://docs.astral.sh/uv/) installed
- **Docker**: For running PostgreSQL database containers

---

### Environment Configuration

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Configure your environment variables:

```ini
# Application Mode
RUN_WORKER=true

# Database (PostgreSQL)
DATABASE_URL=postgresql+asyncpg://renouser:renopass@localhost:5433/renovation_dev
DATABASE_TEST_URL=postgresql+asyncpg://renouser:renopass@localhost:5434/renovation_test

# AI Vision & Inpainting Services
GEMINI_API_KEY=your_gemini_api_key_here
JEV_API_KEY=your_jev_api_key_here

# Storage Backend (Choose 'local' for dev or 's3' for Backblaze B2 / AWS S3 / Cloudflare R2)
STORAGE_BACKEND=local

# Cloud S3 / Backblaze B2 Storage (Required only if STORAGE_BACKEND=s3)
S3_ENDPOINT_URL=https://s3.us-east-005.backblazeb2.com
S3_REGION=us-east-005
S3_BUCKET=renova-prod-files
S3_ACCESS_KEY_ID=0050c525d18bd650000000001
S3_SECRET_ACCESS_KEY=your_application_key_here

# Security
SECRET_KEY=dev_secret_key_change_in_production
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

> [!NOTE]
> **Resilient Storage Fallback**: If `STORAGE_BACKEND=s3` is set but bucket or access keys are missing or invalid, Renova AI automatically falls back to `local` disk storage with a warning log, ensuring the application and PDF generator never crash due to unconfigured cloud credentials.

---

### Cloud Object Storage Setup (Backblaze B2)

Renova AI supports any S3-compatible cloud storage (Backblaze B2, Cloudflare R2, AWS S3, MinIO) to permanently store uploaded photos, segmentation masks, AI design renders, and contractor PDF reports:

1. **Sign Up**: Create a free account at [Backblaze B2](https://www.backblaze.com/cloud-storage) (10 GB free forever, no credit card required).
2. **Create Bucket**:
   - Name: `renova-prod-files` (or your chosen unique name).
   - Visibility: **Private** (all downloads are securely signed by the backend).
   - Note the **Endpoint** (e.g. `s3.us-east-005.backblazeb2.com`) and **Region** (e.g. `us-east-005`).
3. **Generate Application Key**:
   - Go to **Application Keys** &rarr; **Add a New Application Key** (do not use the Master Application Key as S3 clients require a 25-character key ID).
   - Access: **Read and Write** for your bucket.
   - Copy the 25-character **`keyID`** (for `S3_ACCESS_KEY_ID`) and the **`applicationKey`** (for `S3_SECRET_ACCESS_KEY`).
4. **Add to `.env` or Render Dashboard**:
   Set `STORAGE_BACKEND=s3` along with your endpoint, region, bucket, key ID, and secret.

---

### Database Setup

Start the local PostgreSQL instances via Docker Compose:

```bash
docker compose -f infra/docker-compose.yml up -d --wait
```

Run database migrations:

```bash
cd apps/api
uv run alembic upgrade head
```

*(Optional)* Seed sample project data and test accounts:

```bash
uv run python scripts/load_demo_data.py
```

---

### Running Backend & Worker

Open two terminal tabs:

**Terminal 1 — FastAPI Server:**
```bash
cd apps/api
uv run python -m renocore.server
# API running on http://localhost:8000 (Swagger docs at http://localhost:8000/docs)
```

**Terminal 2 — Background Job Runner:**
```bash
cd apps/api
uv run python -m renocore.background.runner
```

---

### Running Frontend

**Terminal 3 — React Client:**
```bash
cd apps/web
pnpm install
pnpm dev
# Web application available at http://localhost:5173
```

---

### Running in Offline / Mock Mode

You can run and test the complete end-to-end user journey in your browser **without Docker or external AI API keys** using Vite's built-in mock mode:

```bash
cd apps/web
pnpm dev:mock
```

### Pre-configured Login Accounts

The system includes **1 Administrator and 3 User accounts** pre-seeded for testing multi-user isolation:

| # | Role / Persona | Email | Password |
|:---:|---|---|---|
| **1** | **Administrator** | `admin@example.com` | `Admin@12345` |
| **2** | **Primary User** | `user@example.com` | `User@12345` |
| **3** | **Homeowner 1** | `user1@example.com` | `User1@12345` |
| **4** | **Homeowner 2** | `user2@example.com` | `User2@12345` |

*(These accounts are automatically seeded into the database on server startup, both in local development and live production environments).*

---

## API Documentation

When the backend is running, interactive Swagger documentation is available at:
`http://localhost:8000/docs`

Key API groups:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/auth/register` | Register a new user account |
| `POST` | `/api/auth/login` | Authenticate and obtain session token |
| `GET` | `/api/projects` | List all renovation projects for current user |
| `POST` | `/api/projects` | Create a new project record |
| `POST` | `/api/projects/{id}/photo` | Upload and validate facade photo |
| `GET` | `/api/projects/{id}/regions` | Retrieve detected facade polygons |
| `PUT` | `/api/projects/{id}/regions` | Save user-edited polygon boundaries |
| `POST` | `/api/projects/{id}/regions/approve` | Finalize regions and progress to scale |
| `GET` | `/api/materials` | Retrieve full materials catalogue |
| `POST` | `/api/projects/{id}/designs` | Create or update material design variant |
| `POST` | `/api/projects/{id}/render` | Trigger photorealistic AI makeover generation |
| `GET` | `/api/designs/{id}/estimate` | Get itemized BOQ calculation (materials, labor, GST) |
| `POST` | `/api/designs/{id}/reports` | Enqueue background job to build architectural PDF report |
| `GET` | `/api/designs/{id}/reports` | List generated report versions for a design |
| `GET` | `/api/reports/{id}/download` | Stream and download contractor-ready PDF report |
| `GET` | `/api/jobs/{id}` | Poll asynchronous background job status (detection, makeover, export) |

---

## Testing & Quality Assurance

The codebase maintains automated test coverage across both frontend and backend suites:

### Frontend Unit & Integration Tests (Vitest)
```bash
cd apps/web
pnpm test          # Runs all 18 test files (159 tests passed)
pnpm typecheck     # TypeScript strict compilation check
pnpm lint          # ESLint code quality analysis
pnpm build         # Production Vite build verification
```

### Backend Unit & Integration Tests (Pytest)
```bash
cd apps/api
uv run pytest apps/api/tests/unit/   # Runs all 441 backend unit tests passed (100%)
```

---

## Repository Layout

```
AI-Renovation/
├── apps/
│   ├── api/                         # FastAPI Backend
│   │   ├── renocore/
│   │   │   ├── background/          # Procrastinate job workers & retry policies
│   │   │   ├── costing/             # Deterministic estimation & price book logic
│   │   │   ├── database/            # Async SQLAlchemy engine & sessions
│   │   │   ├── endpoints/           # REST API routes (auth, projects, materials, estimate)
│   │   │   ├── exports/             # ReportLab PDF report generation
│   │   │   ├── identity/            # Password hashing & JWT token handling
│   │   │   ├── pixels/              # Computer vision, masking & rendering
│   │   │   ├── schemas/             # Pydantic v2 request/response contracts
│   │   │   ├── tables/              # SQLAlchemy database models
│   │   │   └── vision/              # Gemini multimodal vision & Jev clients
│   │   ├── tests/                   # Pytest test suite (unit, integration, golden files)
│   │   └── pyproject.toml           # Python dependencies and tool configs
│   │
│   └── web/                         # React Frontend
│       ├── src/
│       │   ├── api/                 # OpenAPI generated types and TanStack Query hooks
│       │   ├── components/          # Reusable UI components & layout frames
│       │   ├── features/
│       │   │   ├── auth/            # Login & registration forms
│       │   │   ├── estimate/        # BOQ cost table, contractor ranges & PDF download
│       │   │   ├── materials/       # Finish picker, color swatches & design variants
│       │   │   ├── photo/           # Facade photo upload & quality guidance
│       │   │   ├── redesign/        # Before/After comparison slider
│       │   │   ├── regions/         # Konva canvas polygon boundary editor
│       │   │   ├── scale/           # Real-world measurement & dimension calibration
│       │   │   └── wizard/          # Step-by-step progress stepper & state coordinator
│       │   ├── lib/                 # Utility functions, labels & color mappings
│       │   └── mocks/               # In-browser mock API handlers for offline testing
│       ├── tests/                   # Vitest & React Testing Library test suites
│       └── package.json             # Node dependencies and scripts
│
├── infra/                           # Docker Compose (PostgreSQL dev & test instances)
├── samples/                         # Sample house facade photos with open licenses
├── seed/
│   ├── materials.json               # Master catalogue of 22+ finishes and rates
│   ├── make_swatches.py             # Deterministic PIL/NumPy swatch generator
│   └── swatches/                    # 512×512 generated material texture swatches
│
├── Dockerfile                       # Multi-stage production container build
├── render.yaml                      # Render.com deployment configuration
└── README.md                        # Project documentation
```

---

## Deployment

The application is container-ready and configured for single-service or multi-service container deployment:

### Cloud Deployment (Render Blueprint)

The repository includes a ready-to-deploy [`render.yaml`](file:///Users/salesteam/Projects/AI-Renovation/render.yaml) Blueprint:

1. Push your repository to GitHub.
2. In the [Render Dashboard](https://dashboard.render.com), click **New** &rarr; **Blueprint** and connect your repository.
3. Configure the environment secrets:
   - `DATABASE_URL`: Connection string to your cloud PostgreSQL database (e.g. Neon, Supabase, or Render Postgres).
   - `GEMINI_API_KEY`: Google Gemini API key.
   - `JEV_API_KEY`: Jev inpainting/segmentation key.
   - `STORAGE_BACKEND`: Set to `s3` for Backblaze B2, or `local` for ephemeral container storage.
   - `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`: Backblaze B2 credentials (see [Cloud Object Storage Setup](#cloud-object-storage-setup-backblaze-b2)).
4. Click **Apply**: Render automatically builds the multi-stage Docker container, runs database migrations, seeds the 4 default users on startup, and exposes the app with free SSL.

### Production Docker Container
```bash
docker build -t renova-ai .
docker run -p 8000:8000 -p 5173:5173 --env-file .env renova-ai
```

The multi-stage `Dockerfile` compiles the React web application into static assets and bundles it with the FastAPI production server and background worker.

---

## Authors & Acknowledgments

- **Renova AI Team**
- Base architecture derived and adapted from [Jainam2806/renovation](https://github.com/Jainam2806/renovation), with significant enhancements including:
  - New high-contrast Royal Blue & White UI design system and responsive navigation.
  - Architectural categorization system with *Mandatory*, *Opening*, and *Optional* section guides.
  - Added modern architectural elements: Chhajja / Canopy, Louvers / CNC Jali, and Compound Walls.
  - Interactive "Keep Existing (Exclude from Budget)" toggle on facade elements.
  - Expanded 22-item Indian material catalogue (fluted panels, terracotta tiles, granite stone, rustic trowel finishes) with procedural swatch generation.
  - Comprehensive Bill of Quantities (BOQ) with scaffolding, contingency, and GST calculations.
  - Enhanced ReportLab PDF document layout with branded formatting and contractor specifications.

---

*Estimates and visualizations generated by Renova AI are intended for pre-construction planning, contractor briefing, and budget orientation. Formal structural advice and final quotations should always be confirmed on-site with licensed contractors.*

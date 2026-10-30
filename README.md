# DigiPlus — AI-Powered Knowledge & Task Management

DigiPlus turns meeting information into persistent, accountable work. The
application provides meeting and task workflows, AI meeting analysis, and a
searchable knowledge library backed by SQLAlchemy.

## Local development

Backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

The backend health endpoints are `/health` and `/api/health`. Copy the
provided `.env.example` file in each app to a local `.env` file when custom
configuration is needed. Never commit the resulting `.env` files.

## Deployment

Deployment configuration is prepared but has not been deployed or verified.

### Render backend

Create a Render **Web Service** from this repository. Render can read the
included `render.yaml`, or configure the service manually with:

- Root directory: `backend`
- Runtime: Python 3.14.7
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`

Set these Render environment variables:

- `CORS_ORIGINS`: the exact Vercel frontend origin, for example
  `https://your-project.vercel.app`. Multiple origins are comma-separated.
- `DATABASE_URL`: use `sqlite:////var/data/digiplus.db` when a persistent
  disk is mounted at `/var/data`; otherwise the blueprint's
  `sqlite:///./digiplus.db` default is writable but ephemeral.
- `GROQ_API_KEY`: required for `/api/ai/process-notes`; set this secret in
  Render's environment settings. Never commit the key.
- `GROQ_MODEL`: optional model selection, default `openai/gpt-oss-20b`.
- `CLERK_ISSUER`: the Clerk Frontend API issuer URL.
- `CLERK_JWKS_URL`: the matching Clerk Frontend API JWKS URL, ending in
  `/.well-known/jwks.json`.
- `CLERK_AUTHORIZED_PARTIES`: comma-separated exact browser origins authorized
  to use Clerk tokens, including the production Vercel origin and local
  `http://localhost:5173`.

Task status changes require a verified Clerk session. Legacy task owner names
remain display-only and are not treated as authenticated assignments;
authenticated users can claim unassigned tasks. No administrator role is
configured.

### Knowledge library

Knowledge articles are stored in the configured SQLAlchemy database. New
`knowledge_articles` and `knowledge_tags` tables are created automatically at
startup; existing meeting and task tables are not altered for this feature.
Articles are private by default. A `shared` article is visible to every
authenticated Clerk user, while only its creator can edit or delete it.
There is no Clerk organization/team scope or administrator role in the current
application, so shared visibility is application-wide rather than limited to
a Clerk organization.

All Knowledge API operations require a verified Clerk Bearer token. The
creator identity is read from the verified token and cannot be supplied in the
request body. Search supports title/content text, exact category, and exact
tag filters. Related meeting IDs are checked against existing meetings.
Meetings currently have no owner or per-user access field and their existing
API is globally accessible; therefore Knowledge meeting links preserve that
existing global meeting access model.

The frontend Knowledge page supports create, view, edit, delete, category/tag
filtering, and search. From a selected meeting, **Create knowledge draft**
prefills an editable article using the current AI summary, saved summary, or
meeting notes in that order. The article is only persisted after the user
reviews and saves the draft.

Render provides `PORT`; the start command binds Uvicorn to `0.0.0.0:$PORT`.
Database tables are created during application startup. `create_all()` adds
the new Knowledge tables; it is not a general schema migration tool.

SQLite is not inherently durable on a typical stateless Render filesystem:
deploys, restarts, or instance replacement can lose data unless a persistent
disk is attached and `DATABASE_URL` points to it. It also does not suit
multi-instance writes. Persistence on Render has not been verified here.

### Vercel frontend

Import this repository into Vercel and set the project **Root Directory** to
`frontend`. Use the framework preset **Vite**, build command `npm run build`,
and output directory `dist`.

Set this Vercel environment variable for Production (and Preview if desired):

- `VITE_API_BASE_URL`: the public Render URL, for example
  `https://digiplus-api.onrender.com`
- `VITE_CLERK_PUBLISHABLE_KEY`: the Clerk publishable key for the same Clerk
  instance configured on Render. This is a public frontend key, not a secret.

Vite exposes only variables prefixed with `VITE_`; do not put AI keys or other
secrets in Vercel frontend variables. The frontend API client rejects
production requests when this URL is not configured, preventing accidental
requests to localhost.

### Verification after deployment

1. Open `https://<render-service>/health` and confirm the JSON status is `ok`.
2. Open the Render service `/docs` page and create/read a meeting, task, and
   authenticated Knowledge article.
3. Configure Clerk on both deployments, sign in, and verify private/shared
   article access with two distinct test accounts.
4. Open the Vercel URL and use browser developer tools to confirm API calls go
   to the Render origin and do not produce CORS errors.
5. Restart the Render service and verify saved data only if a persistent disk
   has been configured.

# Sous

A kitchen app for two: a master-chef chat that writes recipes, a recipe book, a weekly plan, a deterministic
grocery list with a household "have it / need it" check, a Safeway cart fill, and a step-by-step cook mode.

**Principle (same as Coach Claude):** the model writes and coaches; code does the arithmetic. Merging, scaling and
categorising ingredients (`backend/app/grocery.py`) never touches the LLM.

## Flow
Chef chat -> `save_recipe` -> Recipes -> add to This Week -> grocery list (Have / Need per item)
-> review Safeway matches -> add to cart (never checks out) -> Cook mode.

## Run locally
```bash
cp .env.example .env            # add ANTHROPIC_API_KEY
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
set -a; source ../.env; set +a
.venv/bin/uvicorn app.main:app --port 8100 --reload     # API
cd ../frontend && npm install && npm run dev            # http://localhost:3100
```
Tests: `cd backend && .venv/bin/pytest` and `cd frontend && npm test`.

## Safeway
`SAFEWAY_MODE=mock` (default) returns fake products. `SAFEWAY_MODE=mcp` runs
[`@striderlabs/mcp-safeway`](https://github.com/markswendsen-code/mcp-safeway), which automates safeway.com with
Playwright. It is unofficial and can break when Safeway changes its site or shows a captcha, so each item can fail
without affecting the rest, and the grocery list always works on its own. The app only adds to the cart.

## Deploy (Beelink)
`./deploy_to_beelink.sh` pulls the images GitHub Actions built for `origin/main` and restarts the stack over SSH/Tailscale
(see `deploy.local.env.example`). It serves the UI on :3100 (the API is behind it at `/api`, and not otherwise reachable).
The database and recipe photos live in the `sous_sous_data` volume.

**Backups.** The API snapshots the database daily (14 kept, in the volume). A small `sous-backup` container then copies
the snapshots and the recipe photos to an external drive (`D:\SousBackups` on the Beelink, or `OFFSITE_DIR_ON_BEELINK`),
verifies each copy, and reports to the Recipes page every 10 minutes (it turns red if it goes quiet or fails). It only adds
files, so nothing else on the drive is touched and a deleted photo stays in the backup. If the drive isn't connected the
backup container can't start; the app is unaffected and the deploy script warns. `scripts/host/sous_backup.ps1` does the
same copy by hand from the Beelink if ever needed.

## Google Calendar (optional)
Meals you put on a day are written as timed `Cook: <recipe>` events to a separate **Meals** Google calendar (never
"Care Tasks": the chore sync turns events there into tasks and deletes them). The chef also reads the week's busy
times so it can suggest quick meals on packed evenings. Sous reuses `token_jake.pickle` from Task_Chore_Syncing,
read-only. Locally set `GOOGLE_TOKEN_PATH` in `.env`. On the Beelink set `GOOGLE_TOKEN_FILE_ON_BEELINK` in
`deploy.local.env` and deploy. If the token breaks, re-authenticate in Task_Chore_Syncing; the plan and grocery list
keep working either way.

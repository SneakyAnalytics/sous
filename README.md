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
`./deploy_to_beelink.sh` pulls the images GitHub Actions built for `origin/main` and restarts the stack over SSH/Tailscale (see `deploy.local.env.example`). It serves the UI on :3100 (the API is behind it at `/api`). The database lives in the
`sous_data` volume. Keep `.env` on the Beelink only.

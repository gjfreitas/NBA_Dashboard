# Putting the dashboard online for free

```
GitHub Actions (every 15 min)  ->  Cloudflare R2 (database snapshot)  <-  your computer (stats ingest, now and then)
                                          |
Browser -> Vercel (the site) -> Google Cloud Run (the API; downloads the snapshot, sleeps when nobody visits)
```

Everything below stays inside the free plans. Google Cloud and Cloudflare R2 ask for a card at signup; they only charge past the free limits.
Do the steps in order. Run `python scripts/check_nba_reachability.py` anywhere you doubt a host can reach the NBA first.

## 1. Cloudflare R2 (stores the database)

1. Sign up at cloudflare.com, open **R2 Object Storage**, and add the card when asked (the free plan is 10 GB and 1 million writes a month).
2. **Create bucket**, name it `nba-dashboard`, keep it private.
3. **Manage API tokens -> Create API token**: permission *Object Read & Write*, limited to that bucket. Note the **Account ID**, **Access Key ID** and **Secret Access Key**.

## 2. Upload the first snapshot from your computer

Set the four variables for your user (new terminal afterwards), then push:

```powershell
[Environment]::SetEnvironmentVariable("R2_ACCOUNT_ID", "<account id>", "User")
[Environment]::SetEnvironmentVariable("R2_ACCESS_KEY_ID", "<access key id>", "User")
[Environment]::SetEnvironmentVariable("R2_SECRET_ACCESS_KEY", "<secret>", "User")
[Environment]::SetEnvironmentVariable("R2_BUCKET", "nba-dashboard", "User")
```

```powershell
cd backend
pip install -e ".[cloud]"
python -m nbadash.snapshot push
python -m nbadash.snapshot status
```

## 3. GitHub: the 15-minute refresh

In the repository: **Settings -> Secrets and variables -> Actions -> New repository secret**, one each for
`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, and `THE_ODDS_API_KEY` (all your odds keys, comma separated).

Then **Actions -> Refresh data -> Run workflow** once by hand and read the log. After that it runs by itself.
GitHub switches scheduled workflows off after 60 days without a push; if the site goes stale, check there first.

## 4. Google Cloud Run: the API

1. Create a project at console.cloud.google.com and attach billing (the card; the free tier covers this site).
2. **Billing -> Budgets & alerts**: set a 1 USD budget with email alerts, as a safety net.
3. Install the `gcloud` CLI, run `gcloud auth login` and `gcloud config set project <project id>`, then from the repository root:

```powershell
gcloud run deploy nba-api --source backend --region us-east1 --allow-unauthenticated `
  --memory 1Gi --cpu 1 --max-instances 3 --timeout 3600 `
  --set-env-vars "R2_ACCOUNT_ID=<id>,R2_ACCESS_KEY_ID=<key id>,R2_SECRET_ACCESS_KEY=<secret>,R2_BUCKET=nba-dashboard,NBA_CORS_ORIGINS=*"
```

The command prints the service URL (`https://nba-api-xxxx.a.run.app`). Open `<url>/api/health` and `<url>/api/scoreboard` to check.
`us-east1`, `us-central1` and `us-west1` are the free-tier regions. `--max-instances 3` caps cost if the site gets a rush.

## 5. Vercel: the site

1. vercel.com -> **Add New Project**, import the GitHub repository.
2. **Root Directory: `frontend`**. Add the environment variable `NEXT_PUBLIC_API_URL` = the Cloud Run URL (no trailing slash). Deploy.
3. Tighten the API to your site only (browsers from other origins are then refused):

```powershell
gcloud run services update nba-api --region us-east1 --update-env-vars "NBA_CORS_ORIGINS=https://<your-site>.vercel.app"
```

## 6. Your computer: the stats ingest

`stats.nba.com` refuses GitHub and Google addresses, so player and team game logs are fetched here. Replace the old scheduled task:

```powershell
.\scripts\refresh-task.ps1 install -Minutes 60 -Cloud
```

Each run pulls the newest snapshot, runs the normal refresh (new game logs, standings, shot data), and pushes. When the computer is off the site keeps working;
its player stats just stop moving until the computer is back.

## What to expect

- The first visit after a quiet spell takes a few seconds (the API wakes and downloads about 20 MB).
- Injuries, lineups and odds are at most about 15 to 30 minutes old (GitHub runs late under load). Live games are fetched on demand while someone watches.
- The lineup timing logger does not run in the cloud.
- Odds data: the providers allow showing lines in the app, not republishing them as a feed. Keep `NBA_CORS_ORIGINS` set to your own site.
- Not tested from Google's addresses: whether `cdn.nba.com` answers Cloud Run. Check `<url>/api/scoreboard` right after deploying; if it fails there, tell me.

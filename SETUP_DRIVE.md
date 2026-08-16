# Setting up shared Google Drive storage

This makes deployed-sensor data, analysis results, and alerts persist and
be shared across every visitor of your live app — instead of each browser
tab starting from an empty fleet. See the architecture diagram earlier in
chat: visitors only ever talk to your Streamlit app; the app is the only
thing that holds Google credentials and talks to Drive.

**Skip this entirely and the dashboard still works fine** — it just falls
back to normal per-session behavior (nothing persists, nothing's shared).
`drive_store.py` detects the missing setup automatically and stays silent
about it.

## 1. Create a Google Cloud service account

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and
   create a new project (or pick an existing one) — top-left project
   dropdown → "New Project".
2. In the search bar, type **Google Drive API** → open it → click **Enable**.
3. In the left sidebar: **IAM & Admin → Service Accounts** → **Create
   Service Account**. Give it any name (e.g. `pdm-drive-storage`) → **Create
   and Continue** → skip the optional role/access steps → **Done**.
4. Click into the service account you just created → **Keys** tab →
   **Add Key → Create new key → JSON** → this downloads a `.json` file.
   **Keep this file private — never commit it to GitHub.**

## 2. Convert the key into Streamlit's secrets format

Open the downloaded JSON in a text editor. You'll paste its values into a
`[gcp_service_account]` block like this:

```toml
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\nMIIEvQ...\n-----END PRIVATE KEY-----\n"
client_email = "pdm-drive-storage@your-project-id.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
universe_domain = "googleapis.com"
```

Copy each value straight from the JSON file into the matching line above.
**For `private_key`**, copy it exactly as it appears in the JSON — including
the `\n` characters — as one line in quotes. Don't manually insert real line
breaks.

## 3. Add the secret to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) → open your app →
   **⋮ (menu) → Settings → Secrets**.
2. Paste in the whole `[gcp_service_account]` block from step 2.
3. Click **Save**. The app restarts automatically with the new secret.

## 4. (Optional) See the data file in your own Drive

By default the service account stores the file in its own private Drive
space — the app doesn't need you to do anything else. If you'd like to be
able to open/inspect it yourself in Google Drive's normal UI:

1. In your own Google Drive, create a folder (e.g. "PdM App Data").
2. Right-click → **Share** → paste in the `client_email` value from the
   JSON (looks like `pdm-drive-storage@your-project-id.iam.gserviceaccount.com`)
   → give it **Editor** access.
3. Open that folder and copy its ID from the URL:
   `https://drive.google.com/drive/folders/`**`THIS_PART_IS_THE_ID`**
4. Add one more line to the same secrets block on Streamlit Cloud:
   ```toml
   gcp_drive_folder_id = "paste-the-folder-id-here"
   ```

## 5. Test it locally (optional)

Create `.streamlit/secrets.toml` in your project root with the same
content as steps 2–4 (this path is already in `.gitignore`, so it won't
get committed). Then run:

```bash
streamlit run app/app.py
```

Deploy a sensor or run an analysis, then refresh the page (or open the app
in a private/incognito window) — the data should still be there, since
it's now living on Drive instead of only in that one browser session.

## Troubleshooting

- **Sidebar warning "Shared storage unavailable"** — check the secret block
  is pasted correctly (valid TOML, no missing quotes) and that the Drive
  API is enabled on the right Google Cloud project.
- **"File not found" / permission errors** — double check you enabled the
  Drive API in step 1.2, and if you're using a shared folder (step 4),
  that you shared it with the exact `client_email` address.
- Nothing here can expose your credentials to visitors — they never leave
  the server side of the app.

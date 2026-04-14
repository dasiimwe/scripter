# Scripter

Turn Jinja2 templates into device configuration scripts.

Scripter is a small Flask app for authoring network-config templates once and filling them in repeatedly — either one at a time through a form, or in batches from a CSV.

## Quick start

**macOS / Linux**

```bash
make install    # create venv, install deps, vendor frontend assets
make run        # dev server on http://127.0.0.1:5500
```

**Windows (PowerShell)** — `make` isn't installed by default. Either install it (`winget install ezwinports.make`, `choco install make`, or run under WSL) and use the commands above, **or** run the equivalents natively:

```powershell
# one-time setup
python -m venv .venv
.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
python scripts\fetch_vendor.py

# run
.venv\Scripts\python app.py
```

First run creates `instance\scripter.db` (SQLite) automatically.

## Auth modes

- **Open** — no login, anyone on the URL can manage every script. Good for trusted networks.

  ```bash
  # macOS / Linux
  AUTH_ENABLED=false make run
  ```
  ```powershell
  # Windows PowerShell
  $env:AUTH_ENABLED = "false"; .venv\Scripts\python app.py
  ```

- **Authenticated** (default) — local accounts and/or TACACS+. Admins manage users and auth config via the **Users** and **Auth** links in the top bar. Toggle also available at `/admin/auth-config`.

## What's in it

- **Workbench** — single-pane editor for each script: Run, Details, Template, Fields, History, Outputs.
- **Template editor** — CodeMirror with Jinja2 syntax highlighting, inline validation, "insert snippet" popover, and "detect variables" to auto-create form fields from `{{ var }}` references (including `{% if %}` and `{% for %}`).
- **Fields** — 22 form-field types across three groups (text/numeric/date, choice, and network-specific: IPv4, IPv6, CIDR, MAC, hostname). Drag to reorder. Inline edit per row.
- **IP helper** — type an address in any Run-tab field; get a one-click panel with network, broadcast, netmask, first/last host, and CIDR math. IPv4 and IPv6.
- **IP template helpers** — in a Jinja template, `{{ site_ip.first }}`, `{{ site_ip.netmask }}`, `{{ site_ip.reverse_pointer }}` and more for fields typed as IP/CIDR.
- **Bulk generation** — upload a CSV, preview the rows in an editable table (drop or edit any cell), generate one output per row, grouped into a batch.
- **Outputs library** — `/outputs`. Every run is stored; search, sort, paginate, edit, download, or delete.
- **Audit log** — every edit records who changed what and when; template edits show a line-by-line diff.
- **Themes** — Operator's Manual (warm) and Datasheet (cool white). Persisted in localStorage.

## Production

```bash
# macOS / Linux
SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" make prod
```
```powershell
# Windows PowerShell
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
.venv\Scripts\waitress-serve --listen=0.0.0.0:5500 --threads=8 app:app
```

Runs via waitress on port 5500 with 8 threads. Refuses to start without `SECRET_KEY` set.

## Offline deployment

After the first install (which needs internet once to fetch vendor assets), the app runs entirely offline. All JS, CSS, and fonts are served from `static/vendor/` and `static/fonts/`. No CDN references at runtime.

To refresh vendored assets later:

```bash
# macOS / Linux
make assets
```
```powershell
# Windows
python scripts\fetch_vendor.py
```

## Layout

```
app.py                  Flask app, models, routes, helpers
templates/              Jinja2 templates (workbench.html is the single-pane UI)
static/
  css/                  Stylesheets (workbench.css, fonts.css)
  js/                   iphelper.js, snippets.js, theme.js
  vendor/               CodeMirror, Trix, Sortable, HTMX, Bulma (fetched)
  fonts/                IBM Plex Mono + Newsreader woff2 (fetched)
scripts/fetch_vendor.py Downloads vendor assets at install time
Makefile                install / run / prod / assets / migrate / clean
requirements.txt        Python dependencies
```

## License

See [LICENSE](LICENSE).

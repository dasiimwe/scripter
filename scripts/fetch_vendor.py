#!/usr/bin/env python3
"""Fetch vendored frontend assets for offline use.

Run once (or after version bumps):  make assets
Stdlib-only — no pip deps required.
"""
import io
import pathlib
import shutil
import sys
import tarfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
VENDOR = ROOT / "static" / "vendor"
FONTS = ROOT / "static" / "fonts"

# npm tarballs give us a reproducible, versioned source for every asset.
PACKAGES = {
    "codemirror": {
        "url": "https://registry.npmjs.org/codemirror/-/codemirror-5.65.16.tgz",
        "files": [
            ("package/lib/codemirror.js",         VENDOR / "codemirror" / "codemirror.js"),
            ("package/lib/codemirror.css",        VENDOR / "codemirror" / "codemirror.css"),
            ("package/mode/jinja2/jinja2.js",     VENDOR / "codemirror" / "mode" / "jinja2" / "jinja2.js"),
            ("package/mode/xml/xml.js",           VENDOR / "codemirror" / "mode" / "xml" / "xml.js"),
            ("package/mode/htmlmixed/htmlmixed.js", VENDOR / "codemirror" / "mode" / "htmlmixed" / "htmlmixed.js"),
            ("package/mode/css/css.js",           VENDOR / "codemirror" / "mode" / "css" / "css.js"),
            ("package/mode/javascript/javascript.js", VENDOR / "codemirror" / "mode" / "javascript" / "javascript.js"),
            ("package/addon/edit/matchbrackets.js", VENDOR / "codemirror" / "addon" / "edit" / "matchbrackets.js"),
            ("package/addon/edit/closebrackets.js", VENDOR / "codemirror" / "addon" / "edit" / "closebrackets.js"),
            ("package/addon/search/search.js",    VENDOR / "codemirror" / "addon" / "search" / "search.js"),
            ("package/addon/search/searchcursor.js", VENDOR / "codemirror" / "addon" / "search" / "searchcursor.js"),
            ("package/addon/dialog/dialog.js",    VENDOR / "codemirror" / "addon" / "dialog" / "dialog.js"),
            ("package/addon/dialog/dialog.css",   VENDOR / "codemirror" / "addon" / "dialog" / "dialog.css"),
            ("package/theme/idea.css",            VENDOR / "codemirror" / "theme" / "idea.css"),
        ],
    },
    "trix": {
        "url": "https://registry.npmjs.org/trix/-/trix-2.1.1.tgz",
        "files": [
            ("package/dist/trix.umd.min.js", VENDOR / "trix" / "trix.umd.min.js"),
            ("package/dist/trix.css",        VENDOR / "trix" / "trix.css"),
        ],
    },
    "sortablejs": {
        "url": "https://registry.npmjs.org/sortablejs/-/sortablejs-1.15.2.tgz",
        "files": [
            ("package/Sortable.min.js", VENDOR / "sortablejs" / "Sortable.min.js"),
        ],
    },
    "htmx": {
        "url": "https://registry.npmjs.org/htmx.org/-/htmx.org-1.9.12.tgz",
        "files": [
            ("package/dist/htmx.min.js", VENDOR / "htmx" / "htmx.min.js"),
        ],
    },
    # Kept for legacy admin pages that still extend base.html (Bulma).
    "bulma": {
        "url": "https://registry.npmjs.org/bulma/-/bulma-0.9.4.tgz",
        "files": [
            ("package/css/bulma.min.css", VENDOR / "bulma" / "bulma.min.css"),
        ],
    },
    # Fontsource mirrors Google Fonts with stable, versioned woff2 files.
    "ibm-plex-mono": {
        "url": "https://registry.npmjs.org/@fontsource/ibm-plex-mono/-/ibm-plex-mono-5.0.14.tgz",
        "files": [
            ("package/files/ibm-plex-mono-latin-400-normal.woff2", FONTS / "ibm-plex-mono-400.woff2"),
            ("package/files/ibm-plex-mono-latin-500-normal.woff2", FONTS / "ibm-plex-mono-500.woff2"),
            ("package/files/ibm-plex-mono-latin-600-normal.woff2", FONTS / "ibm-plex-mono-600.woff2"),
            ("package/files/ibm-plex-mono-latin-700-normal.woff2", FONTS / "ibm-plex-mono-700.woff2"),
        ],
    },
    "newsreader": {
        "url": "https://registry.npmjs.org/@fontsource/newsreader/-/newsreader-5.0.19.tgz",
        "files": [
            ("package/files/newsreader-latin-400-normal.woff2", FONTS / "newsreader-400.woff2"),
            ("package/files/newsreader-latin-400-italic.woff2", FONTS / "newsreader-400-italic.woff2"),
            ("package/files/newsreader-latin-500-normal.woff2", FONTS / "newsreader-500.woff2"),
            ("package/files/newsreader-latin-500-italic.woff2", FONTS / "newsreader-500-italic.woff2"),
            ("package/files/newsreader-latin-600-normal.woff2", FONTS / "newsreader-600.woff2"),
        ],
    },
}


def fetch_tarball(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "scripter-fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def extract(pkg_name: str, spec: dict) -> None:
    print(f"  [{pkg_name}] fetching {spec['url'].rsplit('/', 1)[-1]}")
    try:
        data = fetch_tarball(spec["url"])
    except Exception as e:
        print(f"    ! failed: {e}")
        raise
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = {m.name: m for m in tar.getmembers()}
        for src, dst in spec["files"]:
            if src not in members:
                print(f"    ! missing {src} in tarball; skipping")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(members[src]) as f:
                dst.write_bytes(f.read())
            print(f"    → {dst.relative_to(ROOT)}")


def main():
    VENDOR.mkdir(parents=True, exist_ok=True)
    FONTS.mkdir(parents=True, exist_ok=True)
    failures = []
    for name, spec in PACKAGES.items():
        try:
            extract(name, spec)
        except Exception as e:
            failures.append((name, e))
    if failures:
        print("\nFAILED:")
        for name, e in failures:
            print(f"  - {name}: {e}")
        sys.exit(1)
    print("\nAll assets vendored successfully.")


if __name__ == "__main__":
    main()

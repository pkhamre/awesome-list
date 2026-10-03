"""Synchronize this index with pkhamre's public GitHub stars (Python stdlib only)."""

import argparse
from datetime import date
import difflib
import html
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.request import Request, urlopen

from check_index import ENTRY, check

README = Path(__file__).with_name("README.md")


def fetch_stars():
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "awesome-stars-sync",
               "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    repositories = {}
    page = 1
    while True:
        url = f"https://api.github.com/users/pkhamre/starred?per_page=100&page={page}"
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError("GitHub returned an invalid stars page")
        for repo in batch:
            if not isinstance(repo, dict) or not re.fullmatch(r"[\w.-]+/[\w.-]+", repo.get("full_name", ""), re.ASCII):
                raise ValueError("GitHub returned an invalid repository name")
            if not isinstance(repo.get("archived"), bool) or not isinstance(repo.get("description"), (str, type(None))):
                raise ValueError(f"GitHub returned invalid metadata for {repo['full_name']}")
            key = repo["full_name"].casefold()
            if key in repositories:
                raise ValueError("Duplicate stars across pages; stars may have changed during fetch. Retry.")
            repositories[key] = repo
        if len(batch) < 100:
            return repositories
        page += 1


def description(value):
    value = " ".join((value or "").split()) or "Repository description not provided."
    value = html.escape(value, quote=False)
    return re.sub(r"([\\`*_\[\]])", r"\\\1", value)


def row(name, desc):
    return f"- [`{name}`](https://github.com/{name}): {desc}"


def assemble(text, repositories, today):
    check(text)
    prefix, rest = text.split("## Contents\n", 1)
    _, rest = rest.split("## Editor’s picks\n", 1)
    picks, rest = rest.split("## Full index\n", 1)
    index, suffix = rest.split("\n---\n", 1)
    sections = re.split(r"^### (.+)$", index, flags=re.M)
    categories = dict.fromkeys(sections[1::2])
    if "Other projects" not in categories:
        raise ValueError("The index needs an 'Other projects' category for new stars")
    groups = {category: [] for category in categories}
    existing = {}
    for category, body in zip(sections[1::2], sections[2::2]):
        for name, _, desc in ENTRY.findall(body):
            existing[name.casefold()] = (category, desc)
    active = {key: repo for key, repo in repositories.items() if not repo["archived"]}
    # ponytail: new stars need manual categorization; add rules only if review becomes burdensome.
    for key in list(existing) + sorted(active.keys() - existing.keys()):
        if key in active:
            category, desc = existing.get(key, ("Other projects", None))
            repo = active[key]
            groups[category].append(row(repo["full_name"], desc if desc is not None else description(repo["description"])))
    new_picks = [row(active[name.casefold()]["full_name"], desc)
                 for name, _, desc in ENTRY.findall(picks) if name.casefold() in active]
    pick_intro = picks.split("- [`", 1)[0].strip()
    if not new_picks:
        pick_intro = "No editor’s picks in the current stars snapshot."
    elif pick_intro == "No editor’s picks in the current stars snapshot.":
        pick_intro = "The projects I would start with:"
    nav = []
    for category, rows in groups.items():
        anchor = re.sub(r"[^\w\- ]", "", category.lower()).replace(" ", "-")
        nav.append(f"- [{category}](#{anchor}) ({len(rows)})")
    prefix, changed = re.subn(
        r"> Last synchronized: [^\n]+",
        f"> Last synchronized: {today} · {len(active)} non-archived repositories shown; "
        f"{len(repositories) - len(active)} archived repositories omitted", prefix)
    if changed != 1:
        raise ValueError("Expected one synchronization metadata line")
    full_index = sections[0].strip() + "\n\n" + "\n\n".join(
        f"### {category}\n\n" + "\n".join(rows) for category, rows in groups.items())
    result = (prefix + "## Contents\n\n" + "\n".join(nav) + "\n\n## Editor’s picks\n\n"
              + pick_intro + "\n\n" + "\n".join(new_picks) + "\n\n## Full index\n\n"
              + full_index.rstrip() + "\n\n---\n" + suffix)
    check(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print a diff without writing README.md")
    args = parser.parse_args()
    try:
        old = README.read_text(encoding="utf-8")
        check(old)
        new = assemble(old, fetch_stars(), date.today().isoformat())
        if args.dry_run:
            print("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                             fromfile="README.md", tofile="README.md (synced)")), end="")
        elif new != old:
            # Replace only after fetching every page and validating the complete document.
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=README.parent,
                                                 prefix=".README-", delete=False) as file:
                    temporary = Path(file.name)
                    file.write(new)
                temporary.chmod(README.stat().st_mode)
                temporary.replace(README)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            print(check(new))
        else:
            print("Already up to date.")
    except (OSError, ValueError, AssertionError, KeyError, TypeError) as error:
        parser.exit(1, f"Sync failed; README.md unchanged: {error}\n")


if __name__ == "__main__":
    main()

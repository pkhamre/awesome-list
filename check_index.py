"""Check the README's index, counts, navigation, and editor's picks."""

from collections import Counter
from pathlib import Path
import re

ENTRY = re.compile(r"^- \[`([^`]+)`\]\(https://github\.com/([^)]+)\): (.+)$", re.M)


def check(text):
    contents = text.split("## Contents\n", 1)[1].split("## Editor’s picks\n", 1)[0]
    picks = text.split("## Editor’s picks\n", 1)[1].split("## Full index\n", 1)[0]
    index = text.split("## Full index\n", 1)[1].split("\n---\n", 1)[0]
    sections = re.split(r"^### (.+)$", index, flags=re.M)
    names = []
    counts = {}
    for category, body in zip(sections[1::2], sections[2::2]):
        assert category not in counts, f"Duplicate category: {category}"
        entries = ENTRY.findall(body)
        assert len(entries) == len(re.findall(r"^- ", body, re.M)), f"Malformed entry in {category}"
        counts[category] = len(entries)
        for label, target, description in entries:
            assert label == target, f"Link mismatch: {label} -> {target}"
            assert not description.endswith(("moved to", "head over to", "See also", "More info at")), f"Incomplete description: {label}"
            names.append(label.casefold())

    duplicates = [name for name, count in Counter(names).items() if count > 1]
    assert not duplicates, f"Duplicate repositories: {duplicates}"
    nav = re.findall(r"^- \[([^]]+)\]\(#([^)]+)\) \((\d+)\)$", contents, re.M)
    assert [category for category, _, _ in nav] == list(counts), "Contents categories/order differ from index"
    for category, anchor, count in nav:
        expected = re.sub(r"[^\w\- ]", "", category.lower()).replace(" ", "-")
        assert anchor == expected, f"Incorrect anchor: {category}"
        assert int(count) == counts[category], f"Incorrect count: {category}"

    metadata = re.search(r"(\d+) non-archived repositories shown", text)
    assert metadata and int(metadata[1]) == len(names), "Incorrect total count"
    pick_entries = ENTRY.findall(picks)
    assert len(pick_entries) == len(re.findall(r"^- ", picks, re.M)), "Malformed editor's picks"
    assert len({label.casefold() for label, _, _ in pick_entries}) == len(pick_entries), "Duplicate editor's picks"
    for label, target, _ in pick_entries:
        assert label == target and label.casefold() in names, f"Editor’s pick missing from index: {label}"
    return f"OK: {len(names)} unique repositories, {len(counts)} categories, {len(pick_entries)} editor’s picks"


if __name__ == "__main__":
    print(check(Path(__file__).with_name("README.md").read_text(encoding="utf-8")))

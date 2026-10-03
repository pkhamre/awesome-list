"""Offline checks: python3 test_sync_stars.py."""

import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.error import URLError

from check_index import ENTRY, check
import sync_stars as sync

text = sync.README.read_text(encoding="utf-8")
index = text.split("## Full index\n", 1)[1].split("\n---\n", 1)[0]
repositories = {name.casefold(): {"full_name": name, "description": "Changed upstream",
                                 "archived": False} for name, _, _ in ENTRY.findall(index)}
new = sync.assemble(text, repositories, "2026-09-19")
assert new == sync.assemble(new, repositories, "2026-09-19"), "Sync is not idempotent"
new_index = new.split("## Full index\n", 1)[1].split("\n---\n", 1)[0]
assert [line for line in index.splitlines() if line] == [line for line in new_index.splitlines() if line], "Editorial choices changed"

picks = ENTRY.findall(text.split("## Editor’s picks\n", 1)[1].split("## Full index\n", 1)[0])
removed, archived = picks[0][0], picks[1][0]
del repositories[removed.casefold()]
repositories[archived.casefold()]["archived"] = True
repositories["example/new"] = {"full_name": "example/new", "description": "A [tool]\nwith <b>HTML</b> and https://example.com", "archived": False}
new = sync.assemble(text, repositories, "2026-09-20")
assert removed not in new and archived not in new, "Stale index entries or picks survived"
assert "1 archived repositories omitted" in new
assert "Last synchronized: 2026-09-20" in new
other = new.split("### Other projects\n", 1)[1].split("\n---\n", 1)[0]
assert "example/new" in other and r"A \[tool\] with &lt;b&gt;HTML&lt;/b&gt; and https://example.com" in other
assert "Repository description not provided." == sync.description(None)
assert sync.assemble(new, repositories, "2026-09-20") == new
check(sync.assemble(text, {}, "2026-09-20"))  # Empty categories and picks are valid after syncing.

batch = [{"full_name": f"example/repo{i}", "description": None, "archived": False} for i in range(101)]
with patch.object(sync, "urlopen", side_effect=[io.StringIO(json.dumps(batch[:100])), io.StringIO(json.dumps(batch[100:]))]) as request:
    assert len(sync.fetch_stars()) == 101
    assert request.call_count == 2
    assert "page=2" in request.call_args.args[0].full_url
with patch.object(sync, "urlopen", return_value=io.StringIO('{"message": "API error"}')):
    try:
        sync.fetch_stars()
    except ValueError:
        pass
    else:
        raise AssertionError("Accepted malformed API response")

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "README.md"
    path.write_text(text, encoding="utf-8")
    with patch.object(sync, "README", path), patch("sys.argv", ["sync_stars.py", "--dry-run"]), patch.object(sync, "fetch_stars", return_value=repositories), patch("sys.stdout", new=io.StringIO()):
        sync.main()
        assert path.read_text(encoding="utf-8") == text, "Dry run wrote to README"
    with patch.object(sync, "README", path), patch("sys.argv", ["sync_stars.py"]), patch.object(sync, "urlopen", side_effect=[io.StringIO(json.dumps(batch[:100])), URLError("offline")]), patch("sys.stderr", new=io.StringIO()):
        try:
            sync.main()
        except SystemExit as error:
            assert error.code == 1
        else:
            raise AssertionError("Partial fetch should fail")
        assert path.read_text(encoding="utf-8") == text, "Failed fetch changed README"
    with patch.object(sync, "README", path), patch("sys.argv", ["sync_stars.py"]), patch.object(sync, "fetch_stars", return_value=repositories), patch("sys.stdout", new=io.StringIO()):
        sync.main()
        check(path.read_text(encoding="utf-8"))
        assert list(Path(directory).iterdir()) == [path], "Temporary file left behind"

print("OK: pagination, preservation, additions/removals, empty stars, escaping, dry run, and safe writes")

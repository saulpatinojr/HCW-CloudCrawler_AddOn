"""`report.md` is downloaded and opened somewhere else, and it carries text the export's author typed: a resource name,
a tag value, a location. That text must not become Markdown or HTML there (an independent security review of the upload
route found it did: a newline then `# heading`, an image whose address is a tracking beacon, a `<script>`)."""

import copy

import pytest

from cloud_crawler_lab.analysis import markdown_text

from ..conftest import load_sample, make_body, one_claim_decision

EVIL = "x\n# Injected heading\n![b](https://e.example/b.png) <script>alert(1)</script> | `code` [l](https://e.example)"
RAW_MARKERS = ("\n# injected", "<script", "<img", "![b](", "](https://e.example)", "`code`")


def upload(client, export, decision):
    created = client.post("/api/uploads", json=make_body(export, decision))
    assert created.status_code == 201, created.text
    body = created.json()
    headers = {"x-owner-token": body["ownerToken"]}
    files = {
        name: client.get(f"/api/uploads/{body['uploadId']}/files/{name}", headers=headers) for name in body["files"]
    }
    assert all(r.status_code == 200 for r in files.values())
    return files["report.md"].text, files["report.json"].text


def evil_export():
    export = copy.deepcopy(load_sample("sample-resource-graph.json"))
    export["data"][0]["location"] = EVIL
    export["data"][0]["id"] += EVIL
    export["data"][1]["tags"]["env"] = EVIL
    return export


def test_text_from_the_export_and_the_decision_cannot_become_markdown_or_html_in_the_report(client):
    decision = one_claim_decision(statement=EVIL)
    decision["title"] = "T\n# Injected title <img src=x onerror=alert(1)>"
    markdown, report_json = upload(client, evil_export(), decision)
    lowered = markdown.lower()
    for raw in RAW_MARKERS:
        assert raw not in lowered, raw
    assert "&lt;script&gt;" in markdown and "&#96;code&#96;" in markdown
    assert "# Drift report: T" in markdown and "Injected title" in markdown
    rows = [line for line in markdown.splitlines() if line.startswith("| contradicted")]
    assert len(rows) >= 2 and all(line.count("|") == 7 for line in rows), "one finding is one table row"
    assert "injected heading" in report_json.lower(), "the JSON report keeps the text, quoted"


def test_the_report_still_names_the_resources_it_is_about(client):
    markdown, _ = upload(
        client, load_sample("sample-resource-graph.json"), load_sample("decision-zone-redundancy.json")
    )
    assert "hcw-sample-sql-01" in markdown and "hcw-sample-cosmos-prod-01" in markdown
    assert "Not an audit" in markdown, "the closing note is still there"


@pytest.mark.parametrize(
    ("raw", "safe"),
    [
        ("a|b<c>d`e[f]g\\h", "a&#124;b&lt;c&gt;d&#96;e&#91;f&#93;g&#92;h"),
        ("line\r\none\ttwo\x00", "line  one two "),
        ("plain /subscriptions/x-y_z.1 (ok): 1,2;3", "plain /subscriptions/x-y_z.1 (ok): 1,2;3"),
        ("", ""),
    ],
)
def test_markdown_text_replaces_what_markdown_would_read_and_nothing_else(raw, safe):
    assert markdown_text(raw) == safe

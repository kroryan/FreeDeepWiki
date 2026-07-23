import json
from pathlib import Path

from api import fanwiki_library
from api.fanwiki_import import import_dump, inspect_dump


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/" version="0.11">
  <siteinfo>
    <sitename>Test Wiki</sitename>
    <dbname>testwiki</dbname>
    <base>https://example.test/wiki/Main_Page</base>
    <namespaces>
      <namespace key="0" case="first-letter" />
      <namespace key="14" case="first-letter">Category</namespace>
    </namespaces>
  </siteinfo>
  <page>
    <title>Alpha Page</title><ns>0</ns>
    <revision><text xml:space="preserve">Hello [[Beta Page]].</text></revision>
  </page>
  <page>
    <title>Beta Page</title><ns>0</ns>
    <revision><text xml:space="preserve">World [[Category:Tests]].</text></revision>
  </page>
</mediawiki>
"""


def test_import_is_durable_and_uses_valid_article_urls(tmp_path, monkeypatch):
    xml_path = tmp_path / "wiki.xml"
    xml_path.write_text(SAMPLE_XML, encoding="utf-8")
    import_dir = tmp_path / "repos" / "website_example.test"
    monkeypatch.setattr(
        "api.fanwiki_import.website_local_dir",
        lambda _start_url: str(import_dir),
    )

    info = inspect_dump(str(xml_path))
    result = import_dump(str(xml_path), info, {0, 14}, fresh=True)

    assert result["page_count"] == 2
    assert result["links_resolved"] == 1
    meta = json.loads((import_dir / "_site_meta.json").read_text(encoding="utf-8"))
    assert meta["source_type"] == "fanwiki"
    assert meta["wiki_name"] == "Test Wiki"
    assert meta["start_url"] == "https://example.test/wiki/Main_Page"
    assert meta["pages"][0]["url"] == "https://example.test/wiki/Alpha_Page"
    assert "/Main_Page/wiki/" not in meta["pages"][0]["url"]


def test_library_discovers_legacy_import_and_deletes_only_verified_source(
    tmp_path, monkeypatch
):
    repos_dir = tmp_path / "repos"
    imported_dir = repos_dir / "website_legacy.test"
    imported_dir.mkdir(parents=True)
    (imported_dir / "page.md").write_text("content", encoding="utf-8")
    (imported_dir / "_site_meta.json").write_text(
        json.dumps(
            {
                "start_url": "https://legacy.test/wiki/Main_Page",
                "crawled_at": "2026-01-02T03:04:05+00:00",
                "page_count": 1,
                # categories is the compatibility marker used by the original
                # importer before source_type was added.
                "pages": [{"relpath": "page.md", "title": "Page", "categories": []}],
            }
        ),
        encoding="utf-8",
    )
    website_dir = repos_dir / "website_normal.test"
    website_dir.mkdir()
    (website_dir / "_site_meta.json").write_text(
        json.dumps(
            {
                "start_url": "https://normal.test",
                "page_count": 1,
                "pages": [{"relpath": "index.md", "title": "Home"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(fanwiki_library, "get_data_root", lambda: str(tmp_path))
    monkeypatch.setattr(
        fanwiki_library,
        "website_local_dir",
        lambda start_url: str(
            imported_dir if "legacy.test" in start_url else website_dir
        ),
    )

    entries = fanwiki_library.list_all()
    assert len(entries) == 1
    assert entries[0]["repo"] == "legacy.test"
    assert entries[0]["status"] == "imported"
    assert entries[0]["page_count"] == 1

    assert fanwiki_library.delete("https://normal.test") is False
    assert website_dir.is_dir()
    assert fanwiki_library.delete("https://legacy.test/wiki/Main_Page") is True
    assert not imported_dir.exists()

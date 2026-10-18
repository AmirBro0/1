"""Check the actual archive UI with seven isolated metadata fixtures.

All API requests are intercepted inside a fresh browser context. This test never
reads a user key, contacts user API data, uploads video, or invokes a detector.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    args = parser.parse_args()
    if urlsplit(args.url).hostname not in ("127.0.0.1", "localhost"):
        parser.error("Only a local static application may be used")
    items = [
        {
            "job_id": f"pagination-qa-{number}",
            "filename": f"pagination-qa-{number}.mov",
            "status": "done" if number <= 4 else "failed",
            "review_status": "reviewed" if number <= 4 else "not_reviewed",
            "created_at": f"2026-10-18T12:00:0{number}Z",
            "duration_sec": 25,
            "violation_count": 0,
            "archive_status": "partial",
            "asset": {"available": False},
        }
        for number in range(1, 8)
    ]
    checks, queries, errors, mutations = [], [], [], []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def api(route):
            request = route.request
            path = urlsplit(request.url).path
            query = parse_qs(urlsplit(request.url).query, keep_blank_values=True)
            if path == "/ui/v1/session" and request.method == "GET":
                route.fulfill(json={"capabilities": {"formats": [".mov"]}})
                return
            if path.startswith("/ui/v1/runs/") and request.method == "DELETE":
                run_id = path.rsplit("/", 1)[-1]
                mutations.append(run_id)
                items[:] = [item for item in items if item["job_id"] != run_id]
                route.fulfill(json={"deleted": True})
                return
            if path == "/ui/v1/runs" and request.method == "GET":
                selected = list(items)
                for field, name in [("status", "status"), ("review_status", "review_status")]:
                    if name in query:
                        selected = [item for item in selected if item[field] == query[name][0]]
                search = query.get("search", [""])[0]
                selected = [item for item in selected if search.casefold() in item["filename"].casefold()]
                selected.sort(key=lambda item: item["created_at"], reverse=query.get("sort", ["desc"])[0] == "desc")
                limit, offset = int(query.get("limit", [3])[0]), int(query.get("offset", [0])[0])
                queries.append({"limit": limit, "offset": offset, "search": search,
                                "status": query.get("status", [None])[0],
                                "review_status": query.get("review_status", [None])[0]})
                route.fulfill(json={"total": len(selected), "items": selected[offset:offset + limit]})
                return
            raise AssertionError(f"Unexpected isolated API request: {request.method} {path}")

        page.route("**/ui/v1/**", api)
        page.goto(args.url.rstrip("/") + "/#history", wait_until="networkidle")
        page.locator("#archive-scene").wait_for(state="visible")

        def assert_page(number, pages, ids):
            expect(page.locator("#archive-page")).to_have_text(f"{number} / {pages}")
            expect(page.locator(".archive-card")).to_have_count(len(ids))
            expect(page.locator(".archive-card h3")).to_have_text([f"pagination-qa-{item}.mov" for item in ids])
            assert len(ids) <= 3
            assert page.locator("#archive-prev").is_disabled() == (number == 1)
            assert page.locator("#archive-next").is_disabled() == (number == pages)

        def choose(control, value):
            page.locator(f"#{control}").locator("..").locator(".choice-trigger").click()
            page.locator(f'.choice-menu:visible [data-value="{value}"]').click()

        assert_page(1, 3, [7, 6, 5])
        page.locator("#archive-next").click()
        assert_page(2, 3, [4, 3, 2])
        page.locator("#archive-next").click()
        assert_page(3, 3, [1])
        checks.append("seven-records-split-3-3-1-and-disabled-boundaries")
        page.locator("#archive-prev").click()
        assert_page(2, 3, [4, 3, 2])
        page.locator("#archive-prev").click()
        assert_page(1, 3, [7, 6, 5])
        checks.append("previous-navigation-restores-expected-records")

        page.locator("#archive-next").click()
        assert_page(2, 3, [4, 3, 2])
        page.locator("#archive-search").fill("pagination-qa-1")
        assert_page(1, 1, [1])
        page.locator("#archive-search").fill("")
        assert_page(1, 3, [7, 6, 5])
        checks.append("search-starts-at-first-page")

        page.locator("#archive-next").click()
        assert_page(2, 3, [4, 3, 2])
        choose("archive-filter", "done")
        assert_page(1, 2, [4, 3, 2])
        choose("archive-filter", "all")
        assert_page(1, 3, [7, 6, 5])
        page.locator("#archive-next").click()
        assert_page(2, 3, [4, 3, 2])
        choose("archive-review-filter", "reviewed")
        assert_page(1, 2, [4, 3, 2])
        choose("archive-review-filter", "all")
        assert_page(1, 3, [7, 6, 5])
        checks.append("status-and-review-filters-reset-page")

        page.locator("#archive-next").click()
        assert_page(2, 3, [4, 3, 2])
        choose("archive-sort", "asc")
        assert_page(1, 3, [1, 2, 3])
        choose("archive-sort", "desc")
        assert_page(1, 3, [7, 6, 5])
        checks.append("sort-resets-page-and-changes-order")

        page.locator("#archive-next").click()
        assert_page(2, 3, [4, 3, 2])
        page.locator("#archive-next").click()
        assert_page(3, 3, [1])
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator('.archive-card[data-run-id="pagination-qa-1"] button').filter(has_text="Удалить из истории").click()
        assert_page(2, 2, [4, 3, 2])
        expect(page.locator("#archive-status")).to_have_text("Проверок: 6")
        assert mutations == ["pagination-qa-1"]
        checks.append("deleting-last-item-of-last-page-returns-to-valid-page")

        page.locator("#archive-search").fill("no-matching-synthetic-record")
        assert_page(1, 1, [])
        expect(page.locator("#archive-empty")).to_be_visible()
        checks.append("empty-search-has-single-page-and-disabled-navigation")
        archive_queries = [query for query in queries if query["limit"] != 100]
        assert archive_queries and all(query["limit"] == 3 for query in archive_queries)
        assert {query["offset"] for query in archive_queries} == {0, 3, 6}
        assert not errors, errors
        result = {"checks": checks, "passed": len(checks), "javascript_errors": errors,
                  "fixture_records": 7, "archive_request_limit": 3,
                  "offsets": [0, 3, 6], "real_api_requests": 0}
        (ROOT / "qa/archive-pagination-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()

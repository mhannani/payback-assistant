"""Catalog browse endpoint tests (GET /products) — DB-backed against the seeded catalog."""

from __future__ import annotations


async def test_lists_paginated_catalog(api_client) -> None:
    res = await api_client.get("/products?page=1&page_size=5")
    assert res.status_code == 200
    body = res.json()
    assert body["page"] == 1
    assert body["page_size"] == 5
    assert body["total"] > 5  # the seeded catalog is larger than one page
    assert len(body["items"]) == 5
    # The row shape the table renders.
    row = body["items"][0]
    assert {"id", "name", "partner", "partner_name", "price_cents", "tags"} <= row.keys()


async def test_page_window_is_disjoint(api_client) -> None:
    p1 = (await api_client.get("/products?page=1&page_size=10")).json()
    p2 = (await api_client.get("/products?page=2&page_size=10")).json()
    ids1 = {r["id"] for r in p1["items"]}
    ids2 = {r["id"] for r in p2["items"]}
    assert ids1.isdisjoint(ids2)  # different pages return different rows
    assert p1["total"] == p2["total"]  # total is stable across pages


async def test_partner_filter_narrows_results(api_client) -> None:
    all_total = (await api_client.get("/products?page_size=1")).json()["total"]
    dm = (await api_client.get("/products?partner=dm&page_size=1")).json()
    assert 0 < dm["total"] < all_total  # a single partner is a strict subset


async def test_sort_price_low_orders_ascending(api_client) -> None:
    body = (await api_client.get("/products?sort=price_low&page_size=20")).json()
    prices = [r["price_cents"] for r in body["items"]]
    assert prices == sorted(prices)


async def test_invalid_page_size_is_rejected(api_client) -> None:
    assert (await api_client.get("/products?page_size=0")).status_code == 422
    assert (await api_client.get("/products?page_size=999")).status_code == 422

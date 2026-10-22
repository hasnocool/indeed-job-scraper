"""``GET /api/jobs``, ``/api/jobs/facets`` and ``/api/jobs/{short_id}``."""

from __future__ import annotations

import pytest

#: The real dataset in this repository.
TOTAL_JOBS = 98


def test_jobs_total_is_98(client) -> None:
    response = client.get("/api/jobs")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == TOTAL_JOBS
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    assert len(payload["items"]) == 50


def test_jobs_items_have_the_contract_shape(client) -> None:
    payload = client.get("/api/jobs?limit=1").json()
    job = payload["items"][0]
    assert set(job) == {
        "jk",
        "title",
        "company",
        "location",
        "salary",
        "schedule",
        "posted",
        "snippet",
        "url",
        "matches",
        "fingerprint",
        "short_id",
        "status",
        "first_seen",
        "last_seen",
        "seen_count",
        "duplicate_of",
    }
    assert isinstance(job["matches"], list)
    assert isinstance(job["seen_count"], int)
    assert all(isinstance(value, str) for key, value in job.items() if key not in {"matches", "seen_count"})


def test_jobs_never_return_nulls(client) -> None:
    """Missing values are empty strings / empty lists, never null."""
    payload = client.get("/api/jobs?limit=500").json()
    for job in payload["items"]:
        for key, value in job.items():
            assert value is not None, f"{job['jk']}.{key} is null"
        assert isinstance(job["matches"], list)


def test_jobs_pagination(client) -> None:
    first = client.get("/api/jobs?limit=10&offset=0").json()
    second = client.get("/api/jobs?limit=10&offset=10").json()
    assert first["total"] == TOTAL_JOBS
    assert second["total"] == TOTAL_JOBS
    assert len(first["items"]) == 10
    assert len(second["items"]) == 10
    first_ids = {job["jk"] for job in first["items"]}
    second_ids = {job["jk"] for job in second["items"]}
    assert not (first_ids & second_ids)


def test_jobs_offset_past_the_end_is_empty(client) -> None:
    payload = client.get("/api/jobs?limit=10&offset=1000").json()
    assert payload["total"] == TOTAL_JOBS
    assert payload["items"] == []


def test_jobs_total_is_after_filtering(client) -> None:
    payload = client.get("/api/jobs?status=new").json()
    assert payload["total"] < TOTAL_JOBS
    assert all(job["status"] == "new" for job in payload["items"])


def test_jobs_filter_by_status(client) -> None:
    payload = client.get("/api/jobs?status=new&limit=500").json()
    assert payload["total"] == 26
    assert all(job["status"] == "new" for job in payload["items"])


def test_jobs_filter_by_company_is_case_insensitive(client) -> None:
    # "BC Hydro" occurs in the real dataset. The lower-cased needle must match
    # the mixed-case value, and so must the upper-cased one.
    lower = client.get("/api/jobs?company=bc+hydro&limit=500").json()
    assert lower["total"] >= 1
    assert all("bc hydro" in job["company"].lower() for job in lower["items"])

    upper = client.get("/api/jobs?company=BC+HYDRO&limit=500").json()
    assert upper["total"] == lower["total"]
    assert all("bc hydro" in job["company"].lower() for job in upper["items"])


def test_jobs_filter_by_location_is_a_substring_match(client) -> None:
    payload = client.get("/api/jobs?location=Port+Alberni&limit=500").json()
    assert payload["total"] >= 1
    assert all("port alberni" in job["location"].lower() for job in payload["items"])


def test_jobs_free_text_search(client) -> None:
    payload = client.get("/api/jobs?q=Alberni&limit=500").json()
    assert payload["total"] >= 1
    for job in payload["items"]:
        haystack = " ".join(
            job[field] for field in ("title", "company", "location", "snippet", "salary")
        )
        assert "alberni" in haystack.lower()


def test_jobs_filters_combine(client) -> None:
    payload = client.get("/api/jobs?status=new&location=BC&limit=500").json()
    for job in payload["items"]:
        assert job["status"] == "new"
        assert "bc" in job["location"].lower()


def test_jobs_sort_ascending_by_title(client) -> None:
    payload = client.get("/api/jobs?sort=title&order=asc&limit=500").json()
    titles = [job["title"] for job in payload["items"]]
    assert titles == sorted(titles, key=lambda value: value.lower())


def test_jobs_sort_descending_by_title(client) -> None:
    payload = client.get("/api/jobs?sort=title&order=desc&limit=500").json()
    titles = [job["title"] for job in payload["items"]]
    assert titles == sorted(titles, key=lambda value: value.lower(), reverse=True)


def test_jobs_sort_by_last_seen_desc_is_the_default(client) -> None:
    default = client.get("/api/jobs?limit=500").json()["items"]
    explicit = client.get("/api/jobs?sort=last_seen&order=desc&limit=500").json()["items"]
    assert [job["jk"] for job in default] == [job["jk"] for job in explicit]


def test_jobs_limit_is_bounded(client) -> None:
    assert client.get("/api/jobs?limit=0").status_code == 422
    assert client.get("/api/jobs?limit=501").status_code == 422
    assert client.get("/api/jobs?offset=-1").status_code == 422


def test_facets(client) -> None:
    response = client.get("/api/jobs/facets")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == TOTAL_JOBS
    assert "Tofino, BC" in payload["locations"]
    assert "Ucluelet, BC" in payload["locations"]
    assert "Port Alberni, BC" in payload["locations"]
    assert payload["companies"], "there must be real companies"
    assert payload["status_counts"] == {"new": 26, "updated": 6, "unchanged": 66}


def test_facets_lists_are_sorted_and_deduplicated(client) -> None:
    payload = client.get("/api/jobs/facets").json()
    assert payload["locations"] == sorted(set(payload["locations"]))
    assert payload["companies"] == sorted(set(payload["companies"]))


def test_facets_exclude_empty_strings(client) -> None:
    payload = client.get("/api/jobs/facets").json()
    assert "" not in payload["locations"]
    assert "" not in payload["companies"]


def test_get_job_by_short_id(client) -> None:
    listing = client.get("/api/jobs?limit=1").json()
    job = listing["items"][0]
    response = client.get(f"/api/jobs/{job['short_id']}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["short_id"] == job["short_id"]
    assert payload["jk"] == job["jk"]
    assert set(payload) == set(job)


def test_get_job_unknown_short_id_is_404(client) -> None:
    response = client.get("/api/jobs/doesnotexist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}


def test_get_job_unknown_short_id_that_looks_real_is_404(client) -> None:
    response = client.get("/api/jobs/0123456789ab")
    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


@pytest.mark.parametrize("sort", ["last_seen", "first_seen", "title", "company", "salary"])
def test_every_documented_sort_is_accepted(client, sort: str) -> None:
    response = client.get(f"/api/jobs?sort={sort}&order=asc&limit=5")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 5

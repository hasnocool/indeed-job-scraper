"""Search scope, URL construction and cross-location merging."""

from __future__ import annotations

import pytest

from indeed_scraper.config import SearchParams
from indeed_scraper.scraper import Job, merge_job, search_url


def test_default_scope_is_every_job_in_the_bc_locations() -> None:
    params = SearchParams()
    assert params.query == ""
    assert params.locations == ("Ucluelet, BC", "Tofino, BC", "Port Alberni, BC")


def test_search_url_omits_keywords_when_query_is_empty() -> None:
    url = search_url(SearchParams(), "Ucluelet, BC", site="ca.indeed.com")

    assert url.startswith("https://ca.indeed.com/jobs?")
    assert "l=Ucluelet%2C+BC" in url
    assert "q=" not in url
    assert "co=CA" in url


def test_search_url_includes_keywords_page_and_country() -> None:
    url = search_url(
        SearchParams(query="welder"), "Chicago, IL", site="www.indeed.com", start=10
    )

    assert "q=welder" in url
    assert "start=10" in url
    assert "co=US" in url


def test_search_params_strips_and_dedupes_locations() -> None:
    params = SearchParams(locations=(" Tofino, BC ", "Tofino, BC", ""))
    assert params.locations == ("Tofino, BC",)


def test_search_params_requires_a_location() -> None:
    with pytest.raises(ValueError, match="location"):
        SearchParams(locations=())


def test_search_params_rejects_zero_pages() -> None:
    with pytest.raises(ValueError, match="max_pages"):
        SearchParams(max_pages=0)


def test_merge_job_fills_gaps_and_accumulates_matches() -> None:
    first = Job(jk="1", title="Engineer")
    merged = merge_job(first, Job(jk="1", company="Acme"), "Tofino, BC")

    assert merged.title == "Engineer"
    assert merged.company == "Acme"
    assert merged.matches == ("Tofino, BC",)

    again = merge_job(merged, Job(jk="1", title="Senior Engineer"), "Ucluelet, BC")
    assert again.title == "Senior Engineer"
    assert again.matches == ("Tofino, BC", "Ucluelet, BC")


def test_merge_job_without_existing_record_tracks_location() -> None:
    merged = merge_job(None, Job(jk="9", title="Cook"), "Port Alberni, BC")
    assert merged.matches == ("Port Alberni, BC",)

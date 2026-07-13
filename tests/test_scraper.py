"""Offline tests for the SF City Hall lighting scraper.

tests/fixtures/city_hall_page.html is a real capture of the sf.gov page
(July 2026); parsing tests pass a fixed `today` so they stay stable.
"""

from datetime import date
from pathlib import Path

import pytest
from icalendar import Calendar

import scraper

FIXTURE = Path(__file__).parent / "fixtures" / "city_hall_page.html"
FIXTURE_TODAY = date(2026, 7, 10)


# ---------------------------------------------------------------- parse_dates

def test_single_date():
    assert scraper.parse_dates("Friday, January 2, 2026") == [date(2026, 1, 2)]


def test_single_date_without_weekday():
    assert scraper.parse_dates("January 2, 2026") == [date(2026, 1, 2)]


def test_full_range():
    dates = scraper.parse_dates("Sunday, February 1 - Sunday, February 8, 2026")
    assert dates == [date(2026, 2, d) for d in range(1, 9)]


def test_full_range_with_en_dash():
    dates = scraper.parse_dates("Sunday, February 1 – Sunday, February 8, 2026")
    assert dates == [date(2026, 2, d) for d in range(1, 9)]


def test_cross_month_range():
    dates = scraper.parse_dates("Monday, June 29 - Thursday, July 2, 2026")
    assert dates == [
        date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2),
    ]


def test_cross_year_range():
    dates = scraper.parse_dates("Tuesday, December 30 - Friday, January 2, 2026")
    assert dates[0] == date(2025, 12, 30)
    assert dates[-1] == date(2026, 1, 2)
    assert len(dates) == 4


def test_short_range():
    dates = scraper.parse_dates("Monday, March 15-17, 2026")
    assert dates == [date(2026, 3, 15), date(2026, 3, 16), date(2026, 3, 17)]


def test_nbsp_normalization():
    assert scraper.parse_dates("Friday, January 2, 2026") == [date(2026, 1, 2)]


@pytest.mark.parametrize("text", ["", "next Tuesday", "Frobuary 12, 2026", "July"])
def test_unparseable_dates(text):
    assert scraper.parse_dates(text) == []


# ----------------------------------------------------------- parse_event_text

def event(text):
    events = scraper.parse_event_text(text, today=FIXTURE_TODAY)
    assert len(events) == 1
    return events[0]


def test_details_after_plain_hyphen():
    # Current site shape: details follow the colors after a plain " - "
    e = event("Wednesday, July 1, 2026 – teal/pink - in recognition of Cleft Awareness Month")
    assert e == {
        "date": date(2026, 7, 1),
        "colors": "teal/pink",
        "details": "Cleft Awareness Month",
    }


def test_details_after_em_dash():
    e = event("Friday, July 3, 2026 – blue/red – in recognition of National Day of Haiti")
    assert e["colors"] == "blue/red"
    assert e["details"] == "National Day of Haiti"


def test_trailing_hyphen_stripped_from_colors():
    e = event("Wednesday, July 8, 2026 – red - in recognition of LOVB")
    assert e["colors"] == "red"


def test_details_containing_dash_survive():
    e = event("Tuesday, July 28, 2026 – red/gold – Lunar New Year – Year of the Horse")
    assert e["colors"] == "red/gold"
    assert e["details"] == "Lunar New Year – Year of the Horse"


def test_range_event_keeps_details_for_every_date():
    events = scraper.parse_event_text(
        "Wednesday, July 1 - Saturday, July 4, 2026 – blue/pink - "
        "in recognition of SF Bay Area hosting Super Bowl LX",
        today=FIXTURE_TODAY,
    )
    assert len(events) == 4
    assert {e["details"] for e in events} == {"SF Bay Area hosting Super Bowl LX"}
    assert {e["colors"] for e in events} == {"blue/pink"}


def test_non_event_lines_skipped():
    assert scraper.parse_event_text(
        "City Hall will be lit in the month of July for the following:",
        today=FIXTURE_TODAY,
    ) == []
    assert scraper.parse_event_text(
        "Request City Hall lighting in specific colors to honor a cause",
        today=FIXTURE_TODAY,
    ) == []


def test_implausible_dates_dropped():
    assert scraper.parse_event_text(
        "Friday, July 10, 2093 – red - in recognition of a parser bug",
        today=FIXTURE_TODAY,
    ) == []


# -------------------------------------------------- parse_lighting_schedule

def test_fixture_parses_events_with_details():
    html = FIXTURE.read_text(encoding="utf-8")
    events = scraper.parse_lighting_schedule(html, today=FIXTURE_TODAY)

    assert len(events) >= 5
    assert all(e["colors"] for e in events)
    assert all(e["details"] for e in events)

    fourth = next(e for e in events if e["date"] == date(2026, 7, 4))
    assert fourth["colors"] == "red/white/blue"
    assert "America" in fourth["details"]


def test_empty_html_yields_no_events():
    assert scraper.parse_lighting_schedule("<html></html>", today=FIXTURE_TODAY) == []


# ------------------------------------------------------------- CSV merging

E1 = {"date": date(2026, 7, 1), "colors": "red", "details": "Thing A"}
E2 = {"date": date(2026, 7, 2), "colors": "blue", "details": "Thing B"}


def test_merge_adds_new_events():
    merged, added, updated = scraper.merge_events([E1], [E2])
    assert (added, updated) == (1, 0)
    assert merged == [E1, E2]


def test_merge_skips_exact_duplicates():
    merged, added, updated = scraper.merge_events([E1], [dict(E1)])
    assert (added, updated) == (0, 0)
    assert merged == [E1]


def test_merge_updates_edited_details():
    edited = dict(E1, details="Thing A (renamed)")
    merged, added, updated = scraper.merge_events([E1], [edited])
    assert (added, updated) == (0, 1)
    assert merged[0]["details"] == "Thing A (renamed)"


def test_merge_keeps_existing_details_when_new_is_empty():
    merged, _, updated = scraper.merge_events([E1], [dict(E1, details="")])
    assert updated == 0
    assert merged[0]["details"] == "Thing A"


def test_merge_keeps_two_events_on_same_date():
    other = {"date": date(2026, 7, 1), "colors": "green", "details": "Thing C"}
    merged, added, _ = scraper.merge_events([E1], [other])
    assert added == 1
    assert len(merged) == 2


def test_merge_sorts_by_date():
    merged, _, _ = scraper.merge_events([E2], [E1])
    assert [e["date"] for e in merged] == [E1["date"], E2["date"]]


def test_csv_round_trip(tmp_path):
    csv_file = tmp_path / "schedule.csv"
    scraper.save_csv([E1, E2], csv_file)
    assert scraper.load_csv(csv_file) == [E1, E2]


def test_load_csv_missing_file(tmp_path):
    assert scraper.load_csv(tmp_path / "nope.csv") == []


# --------------------------------------------------------------- iCalendar

def test_calendar_events_and_uids():
    same_day = {"date": date(2026, 7, 1), "colors": "blue/gold", "details": "Thing D"}
    cal = scraper.generate_calendar([E1, E2, same_day])
    events = cal.walk("VEVENT")
    assert len(events) == 3

    uids = [str(e["uid"]) for e in events]
    assert len(set(uids)) == 3, f"UIDs must be unique, got {uids}"


def test_calendar_all_day_events():
    cal = scraper.generate_calendar([E1])
    vevent = cal.walk("VEVENT")[0]
    assert vevent["dtstart"].dt == date(2026, 7, 1)
    assert vevent["dtend"].dt == date(2026, 7, 2)
    assert str(vevent["summary"]) == "CHC: red"
    assert str(vevent["description"]) == "Thing A"


def test_calendar_output_is_deterministic():
    assert (
        scraper.generate_calendar([E1, E2]).to_ical()
        == scraper.generate_calendar([E1, E2]).to_ical()
    )


def test_save_calendar_round_trips(tmp_path):
    ics = tmp_path / "calendar.ics"
    scraper.save_calendar(scraper.generate_calendar([E1]), ics)
    parsed = Calendar.from_ical(ics.read_bytes())
    assert len(parsed.walk("VEVENT")) == 1

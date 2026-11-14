"""Offline tests for the SF City Hall lighting scraper.

tests/fixtures/city_hall_page.html is the "Lighting schedule" section of a
real capture of the sf.gov page (July 2026); parsing tests pass a fixed
`today` so they stay stable.
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


def test_cross_year_range_with_both_years():
    dates = scraper.parse_dates("Tuesday, December 29, 2026 - Friday, January 1, 2027")
    assert dates[0] == date(2026, 12, 29)
    assert dates[-1] == date(2027, 1, 1)
    assert len(dates) == 4


def test_short_range():
    dates = scraper.parse_dates("Monday, March 15-17, 2026")
    assert dates == [date(2026, 3, 15), date(2026, 3, 16), date(2026, 3, 17)]


def test_trailing_text_is_not_a_date():
    assert scraper.parse_dates("Friday, January 2, 2026 and then some") == []


def test_nbsp_normalization():
    assert scraper.parse_dates("Friday, January 2, 2026") == [date(2026, 1, 2)]


@pytest.mark.parametrize("text", ["", "next Tuesday", "Frobuary 12, 2026", "July", "June 31, 2026"])
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
        "colors": "Teal/Pink",
        "details": "Cleft Awareness Month",
    }


def test_details_after_em_dash():
    e = event("Friday, July 3, 2026 – blue/red – in recognition of National Day of Haiti")
    assert e["colors"] == "Blue/Red"
    assert e["details"] == "National Day of Haiti"


def test_trailing_hyphen_stripped_from_colors():
    e = event("Wednesday, July 8, 2026 – red - in recognition of LOVB")
    assert e["colors"] == "Red"


def test_details_containing_dash_survive():
    e = event("Tuesday, July 28, 2026 – red/gold – Lunar New Year – Year of the Horse")
    assert e["colors"] == "Red/Gold"
    assert e["details"] == "Lunar New Year – Year of the Horse"


def test_dash_inside_details_after_marker_phrase():
    # Real line (May 2026): the en-dash belongs to the details, not the layout
    e = event(
        "Thursday, July 2, 2026 – Red/White/Red - in recognition of "
        "Peru–United States 200th Anniversary of Diplomatic Relations"
    )
    assert e["colors"] == "Red/White/Red"
    assert e["details"] == "Peru–United States 200th Anniversary of Diplomatic Relations"


@pytest.mark.parametrize("text", [
    # Real lines from the site, each with a different dash layout
    "Sunday, July 5, 2026 - Violet - in recognition of Opening Day",
    "Sunday, July 5, 2026– Violet – in recognition of Opening Day",
    "Sunday, July 5, 2026 –violet- in recognition of Opening Day",
    "Sunday, July 5, 2026 — violet — in recognition of in recognition of Opening Day",
])
def test_any_dash_style(text):
    e = event(text)
    assert e == {"date": date(2026, 7, 5), "colors": "Violet", "details": "Opening Day"}


def test_range_with_en_dash_in_full_line():
    events = scraper.parse_event_text(
        "Wednesday, July 1 – Saturday, July 4, 2026 – red – in recognition of X",
        today=FIXTURE_TODAY,
    )
    assert [e["date"].day for e in events] == [1, 2, 3, 4]
    assert {e["colors"] for e in events} == {"Red"}


def test_short_range_with_en_dash_in_full_line():
    events = scraper.parse_event_text(
        "Monday, July 13–15, 2026 – green – in recognition of X", today=FIXTURE_TODAY
    )
    assert [e["date"].day for e in events] == [13, 14, 15]


def test_event_without_details():
    e = event("Sunday, July 5, 2026 – violet")
    assert e["colors"] == "Violet"
    assert e["details"] == ""


@pytest.mark.parametrize("raw, expected", [
    ("blue/red", "Blue/Red"),
    ("blue/red/ yellow", "Blue/Red/Yellow"),
    ("Dark Blue", "Dark Blue"),
    ("light blue/pink/white", "Light Blue/Pink/White"),
    ("49ers red/gold", "49ers Red/Gold"),
    ("red/yellow/jade (dark green)", "Red/Yellow/Jade (Dark Green)"),
    ("“tie-dye”", "“Tie-Dye”"),
    ("giants’ orange", "Giants’ Orange"),
])
def test_normalize_colors(raw, expected):
    assert scraper.normalize_colors(raw) == expected


def test_range_event_keeps_details_for_every_date():
    events = scraper.parse_event_text(
        "Wednesday, July 1 - Saturday, July 4, 2026 – blue/pink - "
        "in recognition of SF Bay Area hosting Super Bowl LX",
        today=FIXTURE_TODAY,
    )
    assert len(events) == 4
    assert {e["details"] for e in events} == {"SF Bay Area hosting Super Bowl LX"}
    assert {e["colors"] for e in events} == {"Blue/Pink"}


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
    unparsed = []
    events = scraper.parse_lighting_schedule(html, today=FIXTURE_TODAY, unparsed=unparsed)

    assert len(events) == 10
    assert unparsed == []
    assert all(e["colors"] for e in events)
    assert all(e["details"] for e in events)

    fourth = next(e for e in events if e["date"] == date(2026, 7, 4))
    assert fourth["colors"] == "Red/White/Blue"
    assert "America" in fourth["details"]


SECTION = (
    "<details><summary><h3>Lighting schedule</h3></summary><div>{}</div></details>"
)


def test_br_separated_events_in_one_paragraph():
    # Real shape (July 2026): the last June event shared a <p> with the July header
    html = SECTION.format(
        "<p><b>Tuesday, June 30, 2026 – red/white/blue</b> - in recognition of "
        "USA World Cup match on July 1<br/>City Hall will be lit in the month of "
        "<b>July</b> for the following:<br>"
        "<b>Wednesday, July 1, 2026 – teal</b> - in recognition of Cleft Awareness Month</p>"
    )
    unparsed = []
    events = scraper.parse_lighting_schedule(html, today=FIXTURE_TODAY, unparsed=unparsed)
    assert unparsed == []
    assert [(e["date"], e["details"]) for e in events] == [
        (date(2026, 6, 30), "USA World Cup match on July 1"),
        (date(2026, 7, 1), "Cleft Awareness Month"),
    ]


def test_unparseable_event_lines_are_reported():
    html = SECTION.format(
        "<p>City Hall will be lit in the month of July for the following:</p>"
        "<p>Wednesday, July 1, 2026 – teal - in recognition of Cleft Awareness Month</p>"
        "<p>Mon., Jully 6, 2026 – green - in recognition of a typo</p>"
        "<li><p>Friday, July 10, 2026 – blue</p></li>"
    )
    unparsed = []
    events = scraper.parse_lighting_schedule(html, today=FIXTURE_TODAY, unparsed=unparsed)
    assert [e["date"].day for e in events] == [1, 10]  # nested <li><p> not doubled
    assert unparsed == ["Mon., Jully 6, 2026 – green - in recognition of a typo"]


def test_empty_html_yields_no_events():
    assert scraper.parse_lighting_schedule("<html></html>", today=FIXTURE_TODAY) == []


# ------------------------------------------------------------- CSV merging

E1 = {"date": date(2026, 7, 1), "colors": "Red", "details": "Thing A"}
E2 = {"date": date(2026, 7, 2), "colors": "Blue", "details": "Thing B"}
MERGE_TODAY = date(2026, 7, 10)


def merge(existing, new, today=MERGE_TODAY):
    return scraper.merge_events(existing, new, today=today)


def test_merge_adds_new_events():
    merged, added, updated, removed = merge([E1], [E1, E2])
    assert (added, updated, removed) == (1, 0, [])
    assert merged == [E1, E2]


def test_merge_skips_exact_duplicates():
    merged, added, updated, removed = merge([E1], [dict(E1), dict(E1)])
    assert (added, updated, removed) == (0, 0, [])
    assert merged == [E1]


def test_merge_updates_edited_details():
    edited = dict(E1, details="Thing A (renamed)")
    merged, added, updated, _ = merge([E1], [edited])
    assert (added, updated) == (0, 1)
    assert merged[0]["details"] == "Thing A (renamed)"


def test_merge_keeps_existing_details_when_new_is_empty():
    merged, _, updated, _ = merge([E1], [dict(E1, details="")])
    assert updated == 0
    assert merged[0]["details"] == "Thing A"


def test_merge_keeps_two_scraped_events_on_same_date():
    other = {"date": date(2026, 7, 1), "colors": "Green", "details": "Thing C"}
    merged, added, _, removed = merge([E1], [E1, other])
    assert added == 1
    assert removed == []
    assert len(merged) == 2


def test_merge_replaces_corrected_color():
    # The city changed the color for a date: the old row must not linger
    corrected = dict(E1, colors="Red/White/Blue")
    merged, added, _, removed = merge([E1, E2], [corrected, E2])
    assert removed == [E1]
    assert added == 1
    assert merged == [corrected, E2]


def test_merge_color_match_ignores_case():
    merged, added, updated, removed = merge([dict(E1, colors="red")], [E1])
    assert (added, updated, removed) == (0, 1, [])
    assert merged == [E1]


def test_merge_removes_cancelled_future_event():
    cancelled = {"date": date(2026, 7, 20), "colors": "Pink", "details": "Called off"}
    upcoming = {"date": date(2026, 7, 25), "colors": "Gold", "details": "Still on"}
    merged, _, _, removed = merge([E1, cancelled, upcoming], [E1, upcoming])
    assert removed == [cancelled]
    assert merged == [E1, upcoming]


def test_merge_keeps_past_event_the_page_dropped():
    # Past dates that fall off the page are history, not cancellations
    upcoming = {"date": date(2026, 7, 25), "colors": "Gold", "details": "Still on"}
    merged, _, _, removed = merge([E1, upcoming], [upcoming])
    assert removed == []
    assert merged == [E1, upcoming]


def test_merge_keeps_future_event_in_month_not_scraped():
    august = {"date": date(2026, 8, 3), "colors": "Teal", "details": "Next month"}
    merged, _, _, removed = merge([E1, august], [E1])
    assert removed == []
    assert merged == [E1, august]


def test_merge_sorts_by_date():
    merged, _, _, _ = merge([E2], [E1, E2])
    assert [e["date"] for e in merged] == [E1["date"], E2["date"]]


def test_load_csv_normalizes_colors(tmp_path):
    csv_file = tmp_path / "schedule.csv"
    csv_file.write_text("DATE,COLORS,DETAILS\n2026-07-10,blue/red/ yellow,Mongolia\n", encoding="utf-8")
    assert scraper.load_csv(csv_file)[0]["colors"] == "Blue/Red/Yellow"


def test_csv_round_trip(tmp_path):
    csv_file = tmp_path / "schedule.csv"
    scraper.save_csv([E1, E2], csv_file)
    assert scraper.load_csv(csv_file) == [E1, E2]


def test_load_csv_missing_file(tmp_path):
    assert scraper.load_csv(tmp_path / "nope.csv") == []


# --------------------------------------------------------------- iCalendar

def test_calendar_events_and_uids():
    same_day = {"date": date(2026, 7, 1), "colors": "Blue/Gold", "details": "Thing D"}
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
    assert str(vevent["summary"]) == "CHC: Red"
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

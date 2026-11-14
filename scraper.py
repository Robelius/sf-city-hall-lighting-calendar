#!/usr/bin/env python3
"""
SF City Hall Lighting Calendar Scraper
Scrapes the lighting schedule from SF.gov, merges it into the historical CSV,
and regenerates the iCalendar file from the full CSV history.
"""

import csv
import os
import re
import sys
import time
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta, timezone
from icalendar import Calendar, Event
from zoneinfo import ZoneInfo

# Constants
CITY_HALL_URL = "https://www.sf.gov/location--san-francisco-city-hall"
OUTPUT_FILE = "calendar.ics"
CSV_FILE = "lighting_schedule.csv"
DEBUG_HTML_FILE = "debug_page.html"
SCHEDULE_MARKER = "Lighting schedule"
FETCH_ATTEMPTS = 3
FETCH_RETRY_DELAY = 10  # seconds; doubles after each attempt
# Newly scraped dates further than this from today are assumed to be parse bugs
MAX_DATE_DRIFT_DAYS = 400
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

LOCAL_TZ = ZoneInfo("America/Los_Angeles")

# Building blocks for the date at the start of an event line. The city mixes
# hyphens, en-dashes and em-dashes freely, so every dash is treated alike.
WEEKDAY_PREFIX = r'(?:[A-Z][a-z]+day,?\s+)?'
DASH = r'[-–—]'
_MONTH_DAY = WEEKDAY_PREFIX + r'([A-Z][a-z]+)\s+(\d{1,2})'
_YEAR = r',?\s+(\d{4})'
_SEP = r'\s*' + DASH + r'\s*'

# "[Day, ]Month D[, Year] - [Day, ]Month D, Year"
RANGE_RE = re.compile(_MONTH_DAY + r'(?:' + _YEAR + r')?' + _SEP + _MONTH_DAY + _YEAR)
# "[Day, ]Month D-D, Year"
SHORT_RANGE_RE = re.compile(_MONTH_DAY + _SEP + r'(\d{1,2})' + _YEAR)
# "[Day, ]Month D, Year"
SINGLE_RE = re.compile(_MONTH_DAY + _YEAR)

# Stand-in for <br> while extracting text (a unit separator never occurs in the page)
LINE_BREAK = '\x1f'

DETAILS_PREFIX_RE = re.compile(r'\bin recognition of\b\s*', re.IGNORECASE)


def normalize_text(text):
    """Normalize scraped text: unify unicode spaces and collapse whitespace runs"""
    text = re.sub('[\u00a0\u2007\u2009\u202f]', ' ', text)
    text = text.replace('\u200b', '')
    return re.sub(r'\s+', ' ', text).strip()


def normalize_colors(colors):
    """Tidy a colors string and capitalize the first letter of every word.

    "blue/red/ yellow" -> "Blue/Red/Yellow", "49ers red/gold" -> "49ers Red/Gold"
    """
    colors = re.sub(r'\s*/\s*', '/', normalize_text(colors))
    return re.sub(r"(?<![A-Za-z0-9’'])[a-z]", lambda m: m.group().upper(), colors)


def is_event_line(text):
    """Event lines always carry a 4-digit year; headers, links, etc. do not"""
    return bool(re.search(r'\d{4}', text))


def fetch_page():
    """Fetch the SF City Hall webpage with Playwright, retrying on failure.

    A page that loads but lacks the 'Lighting schedule' section (e.g. an AWS
    WAF challenge page) is treated as a retryable failure. On exhaustion the
    last HTML (if any) is saved to DEBUG_HTML_FILE and an error is raised.
    """
    print(f"Fetching page from {CITY_HALL_URL}...")
    last_error = None
    last_html = ""

    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            html_content = _fetch_once()
            if SCHEDULE_MARKER.lower() in html_content.lower():
                print(f"Successfully fetched {len(html_content)} characters")
                return html_content
            last_html = html_content
            last_error = RuntimeError(
                f"Page loaded but does not contain '{SCHEDULE_MARKER}' "
                "(WAF challenge or site layout change?)"
            )
            print(f"Attempt {attempt}/{FETCH_ATTEMPTS}: {last_error}")
        except Exception as e:
            last_error = e
            print(f"Attempt {attempt}/{FETCH_ATTEMPTS} failed: {e}")

        if attempt < FETCH_ATTEMPTS:
            delay = FETCH_RETRY_DELAY * 2 ** (attempt - 1)
            print(f"Retrying in {delay}s...")
            time.sleep(delay)

    if last_html:
        save_debug_html(last_html)
    raise RuntimeError(f"Failed to fetch page after {FETCH_ATTEMPTS} attempts: {last_error}")


def _fetch_once():
    """Single Playwright fetch of the City Hall page, returning the HTML"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={'width': 1280, 'height': 900},
            )
            page = context.new_page()
            page.goto(CITY_HALL_URL, wait_until='domcontentloaded', timeout=60000)
            try:
                # Wait for the schedule section rather than sleeping blindly;
                # the marker check in fetch_page() handles a timeout here
                page.wait_for_selector(f"text={SCHEDULE_MARKER}", timeout=30000)
            except Exception:
                pass
            return page.content()
        finally:
            browser.close()


def save_debug_html(html_content):
    """Save fetched HTML for post-mortem debugging (uploaded as a CI artifact)"""
    with open(DEBUG_HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Saved fetched HTML to {DEBUG_HTML_FILE} for debugging")


def parse_lighting_schedule(html_content, today=None, unparsed=None):
    """Parse the lighting schedule section from the HTML.

    Each event lives in a <p> (or <li>) inside the content that follows the
    'Lighting schedule' <summary>. Note the details text sits OUTSIDE the <b>
    tag (e.g. "<b>Wednesday, July 1, 2026 – teal -</b> in recognition of X"),
    so the whole paragraph must be parsed, not just the bold text. Falls back
    to line-based parsing of the section text if no paragraphs are found.

    If a list is passed as `unparsed`, every line that looks like an event
    (it has a 4-digit year) but could not be parsed is appended to it, so the
    caller can refuse to publish a partial schedule.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    schedule_text_element = soup.find(string=re.compile(SCHEDULE_MARKER, re.IGNORECASE))
    if not schedule_text_element:
        print(f"Warning: Could not find '{SCHEDULE_MARKER}' text anywhere")
        return []

    # Navigate up to the <summary> element, then to its content sibling
    summary_element = schedule_text_element.find_parent('summary')
    if summary_element:
        schedule_content = summary_element.find_next_sibling()
    else:
        print("Warning: Could not find <summary> parent element, using fallback")
        schedule_heading = schedule_text_element.find_parent()
        schedule_content = None
        if schedule_heading:
            schedule_content = schedule_heading.find_next_sibling()
            if not schedule_content and schedule_heading.parent:
                schedule_content = schedule_heading.parent.find_next_sibling()

    if not schedule_content:
        print("Warning: Could not find schedule content")
        return []

    # Primary: one event per paragraph / list item. A <br> inside a paragraph
    # also separates events, so split on those too.
    for br in schedule_content.find_all('br'):
        br.replace_with(LINE_BREAK)
    candidates = [
        line
        for tag in schedule_content.find_all(['p', 'li'])
        for line in tag.get_text().split(LINE_BREAK)
    ]
    if not candidates:
        print("Warning: No <p>/<li> tags found, falling back to line-based parsing")
        candidates = schedule_content.get_text('\n').replace(LINE_BREAK, '\n').splitlines()

    # Nested tags (<li><p>…</p></li>) yield the same text twice
    candidates = list(dict.fromkeys(normalize_text(text) for text in candidates))

    events = []
    for text in candidates:
        parsed = parse_event_text(text, today=today)
        events.extend(parsed)
        if not parsed and is_event_line(text) and unparsed is not None:
            unparsed.append(text)

    if not events:
        print("\nDEBUG: No events found. Showing first few candidate lines:")
        for i, text in enumerate(candidates[:5]):
            print(f"Candidate {i}: {text[:200]}")

    return events


def parse_event_text(event_text, today=None):
    """Parse one line of schedule text into a list of event dicts.

    Expected shape: "<date(s)> – <colors>[ – in recognition of <details>]".
    The date is matched first, so the dash style used anywhere on the line
    (including inside a date range) does not matter. Returns [] for a line
    that is not an event, and also (with a warning) for one that cannot be
    parsed; use is_event_line() to tell the two apart.
    """
    event_text = normalize_text(event_text)

    if not event_text or not is_event_line(event_text):
        return []

    parsed_dates, end = _match_dates(event_text)
    if not parsed_dates:
        print(f"Warning: Could not parse date(s) from: {event_text[:100]}")
        return []

    colors, details = _split_colors_details(event_text[end:])
    if not colors:
        print(f"Warning: Could not find colors in: {event_text[:100]}")
        return []

    # Guard against year/month parsing bugs producing far-off dates
    today = today or date.today()
    for event_date in parsed_dates:
        if abs((event_date - today).days) > MAX_DATE_DRIFT_DAYS:
            print(f"Warning: Dropping line with implausible date {event_date}: {event_text[:100]}")
            return []

    events = []
    for event_date in parsed_dates:
        events.append({
            'date': event_date,
            'colors': colors,
            'details': details,
        })
        print(f"Found event: {event_date} - {colors}" + (f" - {details}" if details else ""))

    return events


def _split_colors_details(rest):
    """Split the text that follows the date into (colors, details)"""
    edge = ' -–—'
    rest = rest.strip(edge)

    prefix = DETAILS_PREFIX_RE.search(rest)
    if prefix:
        colors, details = rest[:prefix.start()], rest[prefix.end():]
        # The city sometimes repeats itself: "in recognition of in recognition of X"
        while DETAILS_PREFIX_RE.match(details):
            details = DETAILS_PREFIX_RE.sub('', details, count=1)
    else:
        # No marker phrase: the first dash separates colors from details. A
        # plain hyphen only counts with a space beside it ("tie-dye" is a color).
        parts = re.split(r'\s*[–—]\s*|\s+-\s*|\s*-\s+', rest, maxsplit=1)
        colors = parts[0]
        details = parts[1] if len(parts) == 2 else ''

    return normalize_colors(colors.strip(edge)), details.strip(edge)


def parse_dates(date_text):
    """Parse a date string that may be a single date or a date range.

    Supports formats like:
    - "Friday, January 2, 2026"
    - "Sunday, February 1 - Sunday, February 8, 2026"
    - "Tuesday, December 29, 2026 - Friday, January 1, 2027"
    - "Monday, March 15-17, 2026"

    Returns a list of date objects, or [] if the whole string is not a date.
    """
    date_text = normalize_text(date_text)
    dates, end = _match_dates(date_text)
    if date_text[end:].strip():
        return []
    return dates


def _match_dates(text):
    """Match the date (or date range) at the start of `text`.

    Returns (dates, end) where `end` is the index just past the date, or
    ([], 0) if the text does not start with a recognizable date.
    """
    try:
        match = RANGE_RE.match(text)
        if match:
            start_month, start_day, start_year, end_month, end_day, year = match.groups()
            end_date = _to_date(end_month, end_day, year)
            start_date = _to_date(start_month, start_day, start_year or year)
            # Range crossing a year boundary with only one year given,
            # e.g. "December 30 - January 2, 2026"
            if start_date > end_date and not start_year:
                start_date = start_date.replace(year=start_date.year - 1)
            return _date_span(start_date, end_date), match.end()

        match = SHORT_RANGE_RE.match(text)
        if match:
            month_name, start_day, end_day, year = match.groups()
            start_date = _to_date(month_name, start_day, year)
            end_date = _to_date(month_name, end_day, year)
            return _date_span(start_date, end_date), match.end()

        match = SINGLE_RE.match(text)
        if match:
            return [_to_date(*match.groups())], match.end()
    except ValueError as e:
        print(f"Warning: Could not parse date in '{text[:60]}': {e}")

    return [], 0


def _to_date(month_name, day, year):
    return datetime.strptime(f"{month_name} {day}, {year}", "%B %d, %Y").date()


def _date_span(start_date, end_date):
    """All dates from start_date to end_date inclusive"""
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def load_csv(filename):
    """Load the historical CSV as a list of event dicts with date objects"""
    if not os.path.exists(filename):
        return []

    events = []
    with open(filename, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Handle both uppercase and lowercase headers for backward compatibility
            date_str = row.get('DATE', row.get('date', ''))
            try:
                event_date = date.fromisoformat(date_str)
            except ValueError:
                print(f"Warning: Skipping CSV row with invalid date: {row}")
                continue
            events.append({
                'date': event_date,
                'colors': normalize_colors(row.get('COLORS', row.get('colors', ''))),
                'details': row.get('DETAILS', row.get('details', '')),
            })
    return events


def merge_events(existing_events, new_events, today=None):
    """Merge newly scraped events into the historical list.

    The scrape is the source of truth for what it covers:
    - On a date the scrape lists, the scraped events replace whatever was
      stored, so a corrected color does not leave the old row behind. (Two
      genuinely different events on one date are both in the scrape, so both
      are kept.) Stored details survive if the scrape has none.
    - A stored event dated today or later, in a month the scrape covers, that
      the scrape no longer lists is treated as cancelled and removed.
    Everything else (past months, and past dates the page has dropped) is
    kept as history.

    Returns the merged list sorted by date, the counts of added and updated
    events, and the list of removed events.
    """
    today = today or date.today()

    def key(event):
        return (event['date'], event['colors'].casefold())

    scraped = {}
    for event in new_events:
        scraped.setdefault(key(event), dict(event))
    scraped_dates = {event_date for event_date, _ in scraped}
    scraped_months = {(d.year, d.month) for d in scraped_dates}

    stored = {key(e): e for e in existing_events}
    merged = {}
    removed = []
    for k, event in stored.items():
        event_date = event['date']
        if event_date in scraped_dates:
            if k not in scraped:
                removed.append(event)  # color corrected, or one of several dropped
        elif event_date >= today and (event_date.year, event_date.month) in scraped_months:
            removed.append(event)  # cancelled
        else:
            merged[k] = dict(event)

    added = updated = 0
    for k, event in scraped.items():
        old = stored.get(k)
        if old is None:
            added += 1
        else:
            if not event['details']:
                event['details'] = old['details']
            if event != old:
                updated += 1
        merged[k] = event

    merged_list = sorted(merged.values(), key=lambda e: (e['date'], e['colors']))
    return merged_list, added, updated, removed


def save_csv(events, filename):
    """Write the full event history to the CSV file"""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['DATE', 'COLORS', 'DETAILS'])
        writer.writeheader()
        for event in events:
            writer.writerow({
                'DATE': event['date'].isoformat(),
                'COLORS': event['colors'],
                'DETAILS': event['details'],
            })
    print(f"CSV saved to {filename} ({len(events)} events)")


def generate_calendar(events):
    """Generate an iCalendar object from the full event history"""
    print(f"\nGenerating calendar with {len(events)} events...")

    cal = Calendar()
    cal.add('prodid', '-//SF City Hall Lighting Calendar//github.com//')
    cal.add('version', '2.0')
    cal.add('X-WR-CALNAME', 'SF City Hall Lighting')
    cal.add('X-WR-CALDESC', 'San Francisco City Hall nightly lighting schedule')
    cal.add('X-WR-TIMEZONE', 'America/Los_Angeles')

    for event_data in events:
        event = Event()
        event_date = event_data['date']

        event.add('summary', f"CHC: {event_data['colors']}")

        # All-day event
        event.add('dtstart', event_date)
        event.add('dtend', event_date + timedelta(days=1))

        description = event_data['details'] if event_data['details'] else 'No details provided'
        event.add('description', description)

        event.add('location', 'San Francisco City Hall, 1 Dr. Carlton B. Goodlett Place, San Francisco, CA 94102')
        event.add('url', CITY_HALL_URL)

        # UID must be unique per event: include the colors so two events on
        # the same date don't collide
        colors_slug = re.sub(r'[^a-z0-9]+', '-', event_data['colors'].lower()).strip('-') or 'event'
        event.add('uid', f"{event_date.isoformat()}-{colors_slug}-cityhall@sf.gov")

        # Stable timestamp so unchanged data produces a byte-identical file
        event.add('dtstamp', datetime(event_date.year, event_date.month, event_date.day, tzinfo=timezone.utc))

        cal.add_component(event)

    return cal


def save_calendar(cal, filename):
    """Validate and save the calendar to a file"""
    ical_bytes = cal.to_ical()
    # Round-trip parse to catch malformed output before publishing it
    Calendar.from_ical(ical_bytes)
    with open(filename, 'wb') as f:
        f.write(ical_bytes)
    print(f"Calendar saved to {filename}")


def main():
    """Main function"""
    print("SF City Hall Lighting Calendar Scraper")
    print("=" * 50)

    # The runner's clock is UTC; the schedule is in Pacific time
    today = datetime.now(LOCAL_TZ).date()

    html_content = fetch_page()
    unparsed = []
    events = parse_lighting_schedule(html_content, today=today, unparsed=unparsed)

    if not events:
        save_debug_html(html_content)
        print("\n✗ Error: No events found in the lighting schedule")
        print("Refusing to update output files; see debug HTML for details")
        sys.exit(1)

    if unparsed:
        save_debug_html(html_content)
        print(f"\n✗ Error: {len(unparsed)} schedule line(s) could not be parsed:")
        for line in unparsed:
            print(f"  - {line[:200]}")
        print("Refusing to publish a partial schedule; see debug HTML for details")
        sys.exit(1)

    existing_events = load_csv(CSV_FILE)
    merged_events, added, updated, removed = merge_events(existing_events, events, today=today)
    for event in removed:
        print(f"Removed (no longer on the schedule): {event['date']} - {event['colors']}")
    print(
        f"\nMerged events: {added} added, {updated} updated, "
        f"{len(removed)} removed, {len(merged_events)} total"
    )
    save_csv(merged_events, CSV_FILE)

    # Regenerate the calendar from the full history so past events survive
    cal = generate_calendar(merged_events)
    save_calendar(cal, OUTPUT_FILE)

    print("\n✓ Calendar successfully generated!")


if __name__ == "__main__":
    main()

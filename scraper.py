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

# Optional weekday prefix like "Sunday, " and dash variants used in date ranges
WEEKDAY_PREFIX = r'(?:[A-Z][a-z]+day,?\s+)?'
DASH = r'[-–—]'


def normalize_text(text):
    """Normalize scraped text: unify unicode spaces and collapse whitespace runs"""
    text = re.sub('[\u00a0\u2007\u2009\u202f]', ' ', text)
    text = text.replace('\u200b', '')
    return re.sub(r'\s+', ' ', text).strip()


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


def parse_lighting_schedule(html_content, today=None):
    """Parse the lighting schedule section from the HTML.

    Each event lives in a <p> (or <li>) inside the content that follows the
    'Lighting schedule' <summary>. Note the details text sits OUTSIDE the <b>
    tag (e.g. "<b>Wednesday, July 1, 2026 – teal -</b> in recognition of X"),
    so the whole paragraph must be parsed, not just the bold text. Falls back
    to line-based parsing of the section text if no paragraphs are found.
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

    # Primary: one event per paragraph / list item
    candidates = [tag.get_text() for tag in schedule_content.find_all(['p', 'li'])]
    if not candidates:
        print("Warning: No <p>/<li> tags found, falling back to line-based parsing")
        candidates = schedule_content.get_text('\n').splitlines()

    events = []
    for text in candidates:
        events.extend(parse_event_text(text, today=today))

    if not events:
        print("\nDEBUG: No events found. Showing first few candidate lines:")
        for i, text in enumerate(candidates[:5]):
            print(f"Candidate {i}: {normalize_text(text)[:200]}")

    return events


def parse_event_text(event_text, today=None):
    """Parse one line of schedule text into a list of event dicts.

    Expected shape: "<date(s)> – <colors>[ – in recognition of <details>]"
    """
    event_text = normalize_text(event_text)

    # Event lines always carry a 4-digit year; skip headers, links, etc.
    if not event_text or not re.search(r'\d{4}', event_text):
        return []

    # Split on em-dash/en-dash delimiters, but NOT plain hyphens which may
    # appear inside date ranges like "February 1 - Sunday, February 8"
    parts = re.split(r'\s*[–—]\s*', event_text)

    if len(parts) < 2:
        print(f"Warning: Could not split event text into parts: {event_text[:100]}")
        return []

    date_part = parts[0].strip()
    colors = parts[1].strip()
    details = ' – '.join(p.strip() for p in parts[2:]).strip()

    # The details often follow the colors after only a plain hyphen (or no
    # dash at all): "teal/pink - in recognition of Cleft Awareness Month"
    if not details:
        inline = re.search(r'\bin recognition of\b\s*', colors, flags=re.IGNORECASE)
        if inline:
            details = colors[inline.end():].strip()
            colors = colors[:inline.start()].strip()
        else:
            hyphen_split = re.split(r'\s+-\s+', colors, maxsplit=1)
            if len(hyphen_split) == 2:
                colors, details = hyphen_split[0].strip(), hyphen_split[1].strip()
    details = re.sub(r'^in recognition of\s+', '', details, flags=re.IGNORECASE)
    # Strip stray delimiter hyphens left at the edges of the colors text
    colors = colors.strip('- ').strip()

    parsed_dates = parse_dates(date_part)
    if not parsed_dates:
        print(f"Warning: Could not parse date(s) from: {date_part}")
        return []

    events = []
    today = today or date.today()
    for event_date in parsed_dates:
        # Guard against year/month parsing bugs producing far-off dates
        if abs((event_date - today).days) > MAX_DATE_DRIFT_DAYS:
            print(f"Warning: Dropping implausible date {event_date} from: {event_text[:100]}")
            continue
        events.append({
            'date': event_date,
            'colors': colors,
            'details': details,
        })
        print(f"Found event: {event_date} - {colors}" + (f" - {details}" if details else ""))

    return events


def parse_dates(date_text):
    """Parse a date string that may be a single date or a date range.

    Supports formats like:
    - "Friday, January 2, 2026"
    - "Sunday, February 1 - Sunday, February 8, 2026"
    - "Monday, March 15-17, 2026"

    Returns a list of date objects.
    """
    date_text = normalize_text(date_text)

    # Date range with two month names: "[Day, ]Month Start - [Day, ]Month End, Year"
    range_match = re.match(
        WEEKDAY_PREFIX + r'([A-Z][a-z]+)\s+(\d{1,2})\s*' + DASH + r'\s*'
        + WEEKDAY_PREFIX + r'([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})',
        date_text
    )
    if range_match:
        start_month, start_day, end_month, end_day, year = range_match.groups()
        try:
            start_date = datetime.strptime(f"{start_month} {start_day}, {year}", "%B %d, %Y").date()
            end_date = datetime.strptime(f"{end_month} {end_day}, {year}", "%B %d, %Y").date()
        except ValueError as e:
            print(f"Warning: Could not parse date range '{date_text}': {e}")
            return []

        # Range crossing a year boundary, e.g. "December 30 - January 2, 2026"
        if start_date > end_date:
            start_date = start_date.replace(year=start_date.year - 1)

        return _date_span(start_date, end_date)

    # Short date range: "[Day, ]Month Start-End, Year"
    short_range_match = re.match(
        WEEKDAY_PREFIX + r'([A-Z][a-z]+)\s+(\d{1,2})\s*' + DASH + r'\s*(\d{1,2}),?\s+(\d{4})',
        date_text
    )
    if short_range_match:
        month_name, start_day, end_day, year = short_range_match.groups()
        dates = []
        for day in range(int(start_day), int(end_day) + 1):
            try:
                dates.append(datetime.strptime(f"{month_name} {day}, {year}", "%B %d, %Y").date())
            except ValueError as e:
                print(f"Warning: Could not parse date '{month_name} {day}, {year}': {e}")
        return dates

    # Single date: "[Day, ]Month Date, Year"
    single_match = re.match(
        WEEKDAY_PREFIX + r'([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})',
        date_text
    )
    if single_match:
        month_name, day, year = single_match.groups()
        try:
            return [datetime.strptime(f"{month_name} {day}, {year}", "%B %d, %Y").date()]
        except ValueError as e:
            print(f"Warning: Could not parse date '{month_name} {day}, {year}': {e}")

    return []


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
                'colors': row.get('COLORS', row.get('colors', '')),
                'details': row.get('DETAILS', row.get('details', '')),
            })
    return events


def merge_events(existing_events, new_events):
    """Merge newly scraped events into the historical list.

    Events are keyed on (date, colors); a re-scraped event with edited details
    updates the existing row instead of creating a duplicate. Returns the
    merged list sorted by date, plus counts of added and updated events.
    """
    merged = {(e['date'], e['colors']): dict(e) for e in existing_events}
    added = updated = 0

    for event in new_events:
        key = (event['date'], event['colors'])
        if key not in merged:
            merged[key] = dict(event)
            added += 1
        elif event['details'] and event['details'] != merged[key]['details']:
            merged[key]['details'] = event['details']
            updated += 1

    merged_list = sorted(merged.values(), key=lambda e: (e['date'], e['colors']))
    return merged_list, added, updated


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

    html_content = fetch_page()
    events = parse_lighting_schedule(html_content)

    if not events:
        save_debug_html(html_content)
        print("\n✗ Error: No events found in the lighting schedule")
        print("Refusing to update output files; see debug HTML for details")
        sys.exit(1)

    existing_events = load_csv(CSV_FILE)
    merged_events, added, updated = merge_events(existing_events, events)
    print(f"\nMerged events: {added} added, {updated} updated, {len(merged_events)} total")
    save_csv(merged_events, CSV_FILE)

    # Regenerate the calendar from the full history so past events survive
    cal = generate_calendar(merged_events)
    save_calendar(cal, OUTPUT_FILE)

    print("\n✓ Calendar successfully generated!")


if __name__ == "__main__":
    main()

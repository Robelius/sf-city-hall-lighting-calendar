#!/usr/bin/env python3
"""
SF City Hall Lighting Calendar Scraper
Scrapes the lighting schedule from SF.gov and generates an iCalendar file
"""

import csv
import os
import re
from bs4 import BeautifulSoup
from datetime import datetime
from icalendar import Calendar, Event
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

# Constants
CITY_HALL_URL = "https://www.sf.gov/location--san-francisco-city-hall"
OUTPUT_FILE = "calendar.ics"
CSV_FILE = "lighting_schedule.csv"
PACIFIC_TZ = ZoneInfo("America/Los_Angeles")


def fetch_page():
    """Fetch the SF City Hall webpage using Playwright (handles JavaScript)"""
    print(f"Fetching page from {CITY_HALL_URL}...")
    
    with sync_playwright() as p:
        # Launch headless browser
        print("Launching browser...")
        browser = p.chromium.launch(headless=True)
        
        # Create a new page
        page = browser.new_page()
        
        # Navigate to the URL
        print("Navigating to page...")
        page.goto(CITY_HALL_URL, wait_until='networkidle', timeout=60000)
        
        # Wait a bit more for any dynamic content to load
        print("Waiting for content to load...")
        page.wait_for_timeout(3000)
        
        # Get the HTML content
        html_content = page.content()
        
        # Close the browser
        browser.close()
        
        print(f"Successfully fetched {len(html_content)} characters")
        return html_content


def parse_lighting_schedule(html_content):
    """Parse the lighting schedule section from the HTML"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find the lighting schedule section
    # The HTML structure is: <details><summary><h3>Lighting schedule</h3></summary><div>content</div></details>
    schedule_text_element = soup.find(string=re.compile(r'Lighting schedule', re.IGNORECASE))
    
    if not schedule_text_element:
        print("Warning: Could not find 'Lighting schedule' text anywhere")
        return []
    
    print(f"Found 'Lighting schedule' text")
    
    # Navigate up to find the <summary> element
    summary_element = schedule_text_element.find_parent('summary')
    
    if not summary_element:
        print("Warning: Could not find <summary> parent element")
        # Fallback: try any parent and get its next sibling
        schedule_heading = schedule_text_element.find_parent()
        if schedule_heading:
            schedule_content = schedule_heading.find_next_sibling()
            if not schedule_content:
                schedule_content = schedule_heading.parent.find_next_sibling()
        else:
            return []
    else:
        print(f"Found <summary> element")
        # Get the next sibling of the summary (should be the content div)
        schedule_content = summary_element.find_next_sibling()
    
    if not schedule_content:
        print("Warning: Could not find schedule content")
        return []
    
    print(f"Schedule content tag: {schedule_content.name}")
    
    # Parse the schedule entries
    events = []
    
    # Find all <b> tags within the schedule content (each event is in a <b> tag)
    event_tags = schedule_content.find_all('b')
    print(f"Found {len(event_tags)} event tags")
    
    # Pattern to match date lines: "Day, Month Date, Year – colors – in recognition of description"
    # Example: "Friday, January 2, 2026 – blue/red – in recognition of National Day of Haiti"
    pattern = r'^([A-Z][a-z]+day),\s+([A-Z][a-z]+)\s+(\d+),\s+(\d{4})\s+[–—-]\s+(.*?)\s+[–—-]\s+in recognition of\s+(.+)$'
    
    for tag in event_tags:
        event_text = tag.get_text().strip()
        
        # Skip empty or non-event text
        if not event_text or 'City Hall' in event_text:
            continue
        
        # Try to match the pattern
        match = re.match(pattern, event_text, re.DOTALL)
        
        if match:
            day_name = match.group(1)
            month_name = match.group(2)
            day = match.group(3)
            year = match.group(4)
            colors = match.group(5).strip()
            details = match.group(6).strip()
            
            # Parse the date
            date_str = f"{month_name} {day}, {year}"
            try:
                event_date = datetime.strptime(date_str, "%B %d, %Y").date()
                
                events.append({
                    'date': event_date,
                    'colors': colors,
                    'details': details
                })
                
                print(f"Found event: {event_date} - {colors} - {details}")
                
            except ValueError as e:
                print(f"Warning: Could not parse date '{date_str}': {e}")
                continue
        else:
            print(f"Warning: Could not parse event text: {event_text[:100]}")
    
    if not events:
        print("\nDEBUG: No events found. Showing first few tags:")
        for i, tag in enumerate(event_tags[:3]):
            print(f"Tag {i}: {tag.get_text()[:200]}")
    
    return events


def generate_calendar(events):
    """Generate an iCalendar file from the events"""
    print(f"\nGenerating calendar with {len(events)} events...")
    
    cal = Calendar()
    cal.add('prodid', '-//SF City Hall Lighting Calendar//github.com//')
    cal.add('version', '2.0')
    cal.add('X-WR-CALNAME', 'SF City Hall Lighting')
    cal.add('X-WR-CALDESC', 'San Francisco City Hall nightly lighting schedule')
    cal.add('X-WR-TIMEZONE', 'America/Los_Angeles')
    
    for event_data in events:
        event = Event()
        
        # Event summary: "CHC: " + colors
        event.add('summary', f"CHC: {event_data['colors']}")
        
        # All-day event
        event.add('dtstart', event_data['date'])
        
        # Description with the details
        event.add('description', event_data['details'])
        
        # Add location
        event.add('location', 'San Francisco City Hall, 1 Dr. Carlton B. Goodlett Place, San Francisco, CA 94102')
        
        # Add URL
        event.add('url', CITY_HALL_URL)
        
        # Generate unique ID
        uid = f"{event_data['date'].isoformat()}-cityhall@sf.gov"
        event.add('uid', uid)
        
        # Add timestamp
        event.add('dtstamp', datetime.now(PACIFIC_TZ))
        
        cal.add_component(event)
    
    return cal


def save_calendar(cal, filename):
    """Save the calendar to a file"""
    with open(filename, 'wb') as f:
        f.write(cal.to_ical())
    print(f"\nCalendar saved to {filename}")


def load_existing_csv(filename):
    """Load existing CSV data and return as a set of tuples (date, colors, details)"""
    if not os.path.exists(filename):
        return set()
    
    existing_events = set()
    with open(filename, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Create a tuple of (date, colors, details) for easy duplicate checking
            # Handle both uppercase and lowercase headers for backward compatibility
            date = row.get('DATE', row.get('date', ''))
            colors = row.get('COLORS', row.get('colors', ''))
            details = row.get('DETAILS', row.get('details', ''))
            existing_events.add((date, colors, details))
    
    return existing_events


def save_to_csv(events, filename):
    """Save events to CSV, appending new entries without duplicates"""
    # Load existing events
    existing_events = load_existing_csv(filename)
    
    # Determine if we need to write headers (new file)
    file_exists = os.path.exists(filename)
    
    # Prepare new events to add
    new_events = []
    duplicate_count = 0
    
    for event in events:
        event_tuple = (
            event['date'].isoformat(),
            event['colors'],
            event['details']
        )
        
        if event_tuple not in existing_events:
            new_events.append(event)
        else:
            duplicate_count += 1
    
    if new_events:
        # Append new events to CSV
        with open(filename, 'a', newline='', encoding='utf-8') as f:
            fieldnames = ['DATE', 'COLORS', 'DETAILS']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            # Write header if new file
            if not file_exists:
                writer.writeheader()
            
            # Write new events
            for event in new_events:
                writer.writerow({
                    'DATE': event['date'].isoformat(),
                    'COLORS': event['colors'],
                    'DETAILS': event['details']
                })
        
        print(f"\nCSV updated: {len(new_events)} new event(s) added to {filename}")
    else:
        print(f"\nCSV unchanged: All events already exist in {filename}")
    
    if duplicate_count > 0:
        print(f"Skipped {duplicate_count} duplicate event(s)")


def main():
    """Main function"""
    print("SF City Hall Lighting Calendar Scraper")
    print("=" * 50)
    
    try:
        # Fetch the webpage
        html_content = fetch_page()
        
        # Parse the lighting schedule
        events = parse_lighting_schedule(html_content)
        
        if not events:
            print("\nWarning: No events found in the lighting schedule")
            print("The calendar file may be empty or contain only previous events")
        
        # Save to CSV (append without duplicates)
        save_to_csv(events, CSV_FILE)
        
        # Generate the calendar
        cal = generate_calendar(events)
        
        # Save to file
        save_calendar(cal, OUTPUT_FILE)
        
        print("\n✓ Calendar successfully generated!")
        print(f"Subscribe to: https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/{OUTPUT_FILE}")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise


if __name__ == "__main__":
    main()

# SF City Hall Lighting Calendar

A calendar subscription for San Francisco City Hall's nightly lighting schedule.

## About

San Francisco City Hall is illuminated with different colored lights throughout the year to honor various causes, celebrations, and events. This project automatically scrapes the [official SF City Hall website](https://www.sf.gov/location--san-francisco-city-hall) on the 1st and 2nd of each month (when the city posts the new schedule) plus weekly on Mondays (to catch mid-month additions), and generates an up-to-date calendar subscription file.

## Subscribe to the Calendar

Add this calendar to your preferred calendar application:

```
https://raw.githubusercontent.com/Robelius/sf-city-hall-lighting-calendar/main/calendar.ics
```

### How to Subscribe

#### Apple Calendar (macOS/iOS)
1. Open Calendar app
2. Go to File → New Calendar Subscription (macOS) or Settings → Accounts → Add Account → Other → Add Subscribed Calendar (iOS)
3. Paste the URL above
4. Set refresh frequency (recommended: daily)

#### Google Calendar
1. Open [Google Calendar](https://calendar.google.com)
2. Click the "+" next to "Other calendars" on the left
3. Select "From URL"
4. Paste the URL above
5. Click "Add calendar"

#### Outlook
1. Open Outlook Calendar
2. Go to Add Calendar → Subscribe from web
3. Paste the URL above
4. Name it "SF City Hall Lighting"
5. Click Import

#### Other Calendar Apps
Most calendar applications support iCalendar (.ics) subscriptions. Look for "Subscribe to calendar" or "Add calendar from URL" options.

## Event Format

Each calendar event includes:
- **Title**: `CHC: [Colors]` (e.g., "CHC: Blue/Red")
- **Date**: All-day event on the lighting date
- **Description**: Details about what the lighting honors
- **Location**: San Francisco City Hall address

## Historical Data (CSV)

All scraped events are also saved to [`lighting_schedule.csv`](lighting_schedule.csv) for historical reference. The CSV file contains:
- **DATE**: ISO format date (YYYY-MM-DD)
- **COLORS**: The lighting colors for that date, with each word capitalized (e.g. `Red/White/Blue`)
- **DETAILS**: Description of what the lighting honors

The CSV file accumulates all events over time without duplicates, providing a complete historical record of City Hall lighting schedules. March–June 2026 was backfilled from Wayback Machine snapshots of the city's page.

## How It Works

1. A GitHub Action runs on the 1st and 2nd of each month, plus weekly on Mondays, at 12pm PST
2. The Python scraper fetches the SF City Hall website (with retries and WAF-challenge detection)
3. It extracts the lighting schedule for the current month
4. Merges the scraped events into the CSV file. The city's page is the source of truth for the dates it lists: edited details and corrected colors replace the stored row, and an upcoming event that disappears from the current month's schedule is removed as cancelled. Past events stay as history.
5. Regenerates the iCalendar (.ics) file from the full CSV history, so past events are preserved
6. Commits the updated files to the repository
7. Your subscribed calendar automatically syncs the changes

If the scrape finds no events (site down, layout change, WAF block), or if any line of the schedule cannot be parsed, the run fails loudly instead of committing an empty or partial calendar, and the fetched HTML is uploaded as a workflow artifact for debugging.

## Technical Details

- **Scraper**: Python with Playwright (headless browser) and BeautifulSoup for HTML parsing
- **Calendar Format**: iCalendar (.ics) standard, regenerated from the CSV history on every run
- **Automation**: GitHub Actions (cron: 1st/2nd of the month + weekly on Mondays)
- **Timezone**: America/Los_Angeles (Pacific Time)
- **Tests**: `pip install -r requirements-dev.txt && pytest` — offline tests against a saved copy of the schedule section in `tests/fixtures/`, run in CI on every push
- **Note**: Uses Playwright because SF.gov requires JavaScript execution to bypass AWS WAF protection

## Data Source

All lighting schedule information is sourced from the official [SF City Hall website](https://www.sf.gov/location--san-francisco-city-hall).

## Contributing

Found a bug or have a suggestion? Please open an issue!

## License

See [LICENSE](LICENSE) file for details.

---

**Note**: The lighting schedule is updated on the first of each month by the City of San Francisco. This calendar automatically syncs those updates on the 1st and 2nd of each month, and checks weekly for mid-month additions.

# SF City Hall Lighting Calendar

A calendar subscription for San Francisco City Hall's nightly lighting schedule.

## About

San Francisco City Hall is illuminated with different colored lights throughout the year to honor various causes, celebrations, and events. This project automatically scrapes the [official SF City Hall website](https://www.sf.gov/location--san-francisco-city-hall) on the 1st and 2nd of each month (when the city posts the new schedule) plus weekly on Mondays (to catch mid-month additions), and generates an up-to-date calendar subscription file.

## Subscribe to the Calendar

Add this calendar to your preferred calendar application:

```
https://raw.githubusercontent.com/robelius/sf-city-hall-lighting-calendar/main/calendar.ics
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
- **Title**: `CHC: [Colors]` (e.g., "CHC: blue/red")
- **Date**: All-day event on the lighting date
- **Description**: Details about what the lighting honors
- **Location**: San Francisco City Hall address

## Historical Data (CSV)

All scraped events are also saved to [`lighting_schedule.csv`](lighting_schedule.csv) for historical reference. The CSV file contains:
- **date**: ISO format date (YYYY-MM-DD)
- **colors**: The lighting colors for that date
- **details**: Description of what the lighting honors

The CSV file accumulates all events over time without duplicates, providing a complete historical record of City Hall lighting schedules.

## How It Works

1. A GitHub Action runs on the 1st and 2nd of each month, plus weekly on Mondays, at 12pm PST
2. The Python scraper fetches the SF City Hall website (with retries and WAF-challenge detection)
3. It extracts the lighting schedule for the current month
4. Merges new events into the CSV file (deduplicated; edited details update the existing row)
5. Regenerates the iCalendar (.ics) file from the full CSV history, so past events are preserved
6. Commits the updated files to the repository
7. Your subscribed calendar automatically syncs the changes

If the scrape finds no events (site down, layout change, WAF block), the run fails loudly instead of committing an empty calendar, and the fetched HTML is uploaded as a workflow artifact for debugging.

## Technical Details

- **Scraper**: Python with Playwright (headless browser) and BeautifulSoup for HTML parsing
- **Calendar Format**: iCalendar (.ics) standard, regenerated from the CSV history on every run
- **Automation**: GitHub Actions (cron: 1st/2nd of the month + weekly on Mondays)
- **Timezone**: America/Los_Angeles (Pacific Time)
- **Tests**: `pip install -r requirements-dev.txt && pytest` — offline tests against a saved HTML fixture in `tests/fixtures/`, run in CI on every push
- **Note**: Uses Playwright because SF.gov requires JavaScript execution to bypass AWS WAF protection

## Data Source

All lighting schedule information is sourced from the official [SF City Hall website](https://www.sf.gov/location--san-francisco-city-hall).

## Contributing

Found a bug or have a suggestion? Please open an issue!

## License

See [LICENSE](LICENSE) file for details.

---

**Note**: The lighting schedule is updated on the first of each month by the City of San Francisco. This calendar automatically syncs those updates on the 1st and 2nd of each month, and checks weekly for mid-month additions.

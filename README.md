# SF City Hall Lighting Calendar

A calendar subscription for San Francisco City Hall's nightly lighting schedule.

## About

San Francisco City Hall is illuminated with different colored lights throughout the year to honor various causes, celebrations, and events. This project automatically scrapes the [official SF City Hall website](https://www.sf.gov/location--san-francisco-city-hall) daily and generates an up-to-date calendar subscription file. 

*I plan to reduce the frequency once I know this actually works.*

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

1. A GitHub Action runs daily at 1pm PST
2. The Python scraper fetches the SF City Hall website
3. It extracts the lighting schedule for the current month
4. Appends new events to the CSV file (without duplicates)
5. Generates an iCalendar (.ics) file with all events
6. Commits the updated files to the repository
7. Your subscribed calendar automatically syncs the changes

## Manual Update

You can manually trigger the calendar update:

1. Go to the **Actions** tab in this repository
2. Click on "Update SF City Hall Lighting Calendar"
3. Click "Run workflow"

### Prerequisites

- Python 3.11 or higher
- pip

### Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/sf-city-hall-lighting-calendar.git
cd sf-city-hall-lighting-calendar

# Install dependencies
pip install -r requirements.txt

# Run the scraper
python scraper.py
```

This will generate:
- `calendar.ics` - iCalendar subscription file
- `lighting_schedule.csv` - Historical data in CSV format

## Technical Details

- **Scraper**: Python with BeautifulSoup for HTML parsing
- **Calendar Format**: iCalendar (.ics) standard
- **Automation**: GitHub Actions (daily cron job)
- **Timezone**: America/Los_Angeles (Pacific Time)

## Data Source

All lighting schedule information is sourced from the official [SF City Hall website](https://www.sf.gov/location--san-francisco-city-hall).

## Contributing

Found a bug or have a suggestion? Please open an issue!

## License

See [LICENSE](LICENSE) file for details.

---

**Note**: The lighting schedule is updated monthly by the City of San Francisco. This calendar automatically syncs those updates daily.

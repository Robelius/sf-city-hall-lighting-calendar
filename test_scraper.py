#!/usr/bin/env python3
"""Test script to debug the scraper"""

import re
import requests
from bs4 import BeautifulSoup

CITY_HALL_URL = "https://www.sf.gov/location--san-francisco-city-hall"

print("Fetching page...")
response = requests.get(CITY_HALL_URL, timeout=30)
response.raise_for_status()

soup = BeautifulSoup(response.text, 'html.parser')

# Find the lighting schedule section
schedule_heading = soup.find(['h3', 'h2'], string=re.compile(r'Lighting schedule', re.IGNORECASE))

if not schedule_heading:
    print("ERROR: Could not find 'Lighting schedule' heading")
    exit(1)

print(f"Found heading: {schedule_heading.get_text()}")

# Get the content after the heading
schedule_content = schedule_heading.find_next_sibling()

if not schedule_content:
    print("ERROR: Could not find schedule content")
    exit(1)

print(f"\nSchedule content tag: {schedule_content.name}")
print(f"\nSchedule content (first 1000 chars):")
print("=" * 80)
print(schedule_content.get_text()[:1000])
print("=" * 80)

# Try to find all the date patterns
schedule_text = schedule_content.get_text()
print(f"\nFull schedule text length: {len(schedule_text)} characters")

# Try different patterns
print("\n\nTrying to match patterns:")
print("=" * 80)

# Pattern 1: Original strict pattern
pattern1 = r'([A-Z][a-z]+day),\s+([A-Z][a-z]+)\s+(\d+),\s+(\d{4})\s+–\s+(.*?)\s+–\s+in recognition of\s+(.*?)(?=\n|$)'
matches1 = list(re.finditer(pattern1, schedule_text, re.MULTILINE))
print(f"Pattern 1 (strict 'in recognition of'): {len(matches1)} matches")

# Pattern 2: More flexible
pattern2 = r'([A-Z][a-z]+day),\s+([A-Z][a-z]+)\s+(\d+),\s+(\d{4})\s+–\s+(.*?)(?=\n|$)'
matches2 = list(re.finditer(pattern2, schedule_text, re.MULTILINE))
print(f"Pattern 2 (flexible): {len(matches2)} matches")

if matches2:
    print("\nFirst few matches with Pattern 2:")
    for i, match in enumerate(matches2[:3]):
        print(f"\nMatch {i+1}:")
        print(f"  Full match: {match.group(0)}")

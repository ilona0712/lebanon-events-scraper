"""
Lebanese Events Scraper
Scrapes events from multiple Lebanese sources: ihjoz.com, lebtivity.com, ticketingboxoffice.com
Features: async scraping, geocoding, deduplication, CSV export
"""

import asyncio
import json
import re
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import asyncio

def clean_text(text):
    """Remove extra whitespace and clean text"""
    return ' '.join(text.split()).strip()

def extract_date_time(text):
    """Try to extract and normalize date/time from various formats"""
    if not text:
        return "Date/Time not specified"
    
    # Try to find common date patterns
    patterns = [
        r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})',  # 8 February 2026
        r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})',  # February 8, 2026
        r'(\d{1,2})/(\d{1,2})/(\d{4})',  # 08/02/2026
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return text.strip()
    
    return clean_text(text)

async def geocode_location(page, location_name):
    """Get latitude and longitude for a location using OpenStreetMap Nominatim"""
    if not location_name or location_name in ["Lebanon", "Location not specified", "N/A"]:
        return None, None
    
    try:
        # Clean location name and add Lebanon context
        clean_location = clean_text(location_name)
        search_query = f"{clean_location}, Lebanon"
        
        # Use Nominatim API (free, no API key needed)
        nominatim_url = f"https://nominatim.openstreetmap.org/search?q={search_query}&format=json&limit=1"
        
        await page.goto(nominatim_url, wait_until="networkidle", timeout=30000)
        content = await page.content()
        
        # Extract JSON from page
        soup = BeautifulSoup(content, "html.parser")
        json_text = soup.get_text()
        
        try:
            data = json.loads(json_text)
            if data and len(data) > 0:
                lat = float(data[0].get('lat'))
                lon = float(data[0].get('lon'))
                print(f"    📍 Geocoded: {location_name} -> ({lat}, {lon})")
                return lat, lon
        except:
            pass
    
    except Exception as e:
        print(f"    ⚠️ Geocoding failed for {location_name}: {e}")
    
    return None, None

async def scrape_ihjoz(page, url, results):
    """Scrape ihjoz.com - similar to NNA pattern: list then details"""
    
    if url in results["visited_urls"]:
        return
    results["visited_urls"].add(url)
    
    print(f"  --> Scraping ihjoz: {url}")
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        
        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")
        
        # Check if this is the main page or event detail page
        if "/events/" in url:
            # This is an event detail page
            if "ihjoz_details" not in results:
                results["ihjoz_details"] = {}
            
            # Extract title
            title_elem = soup.select_one("div.event-card-title h1, h1.event-card-title-text")
            if not title_elem:
                title_elem = soup.select_one("h1")
            
            title = clean_text(title_elem.get_text()) if title_elem else "No title"
            
            # Extract date/time
            date_elem = soup.select_one("div.event-date, .event-card-date")
            date_time = extract_date_time(date_elem.get_text()) if date_elem else "Date not found"
            
            # Extract location
            location_elem = soup.select_one("div[class*='location'], div[class*='venue']")
            if not location_elem:
                location_elem = soup.select_one("div.event-card-info div")
            location = clean_text(location_elem.get_text()) if location_elem else "Location not specified"
            
            # Extract description
            desc_container = soup.select_one("div.event-card-description")
            if desc_container:
                all_text = []
                for elem in desc_container.find_all(['p', 'div']):
                    text = clean_text(elem.get_text())
                    if len(text) > 20:
                        all_text.append(text)
                description = "\n\n".join(all_text) if all_text else "Description not available"
            else:
                description = "Description not available"
            
            results["ihjoz_details"][url] = {
                "title": title,
                "date_time": date_time,
                "location": location,
                "description": description,
                "url": url
            }
            
        else:
            # This is a list page - find all event links
            if "ihjoz_list" not in results:
                results["ihjoz_list"] = []
            
            # Find event cards
            event_cards = soup.select("div.event-card, div[class*='event-card']")
            
            for card in event_cards:
                # Find the link to event detail
                link_elem = card.select_one("a[href*='/events/']")
                if link_elem and 'href' in link_elem.attrs:
                    event_url = urljoin(url, link_elem['href'])
                    
                    # Get title from h1 inside the card
                    title_elem = card.select_one("h1, div.event-card-title-truncated, .event-card-title")
                    title = clean_text(title_elem.get_text()) if title_elem else "No title"
                    
                    results["ihjoz_list"].append({
                        "url": event_url,
                        "title": title
                    })
                    
                    # Add to visit queue
                    if event_url not in results["visited_urls"]:
                        results["to_visit"].append(event_url)
    
    except Exception as e:
        print(f"      Error scraping ihjoz {url}: {e}")

async def scrape_lebtivity(page, url, results):
    """Scrape lebtivity.com"""
    
    if url in results["visited_urls"]:
        return
    results["visited_urls"].add(url)
    
    print(f"  --> Scraping lebtivity: {url}")
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        
        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")
        
        if "lebtivity_events" not in results:
            results["lebtivity_events"] = []
        
        # Find event cards
        event_cards = soup.select("div.maincard-meta, div[class*='maincard'], div[class*='event']")
        
        for card in event_cards:
            try:
                # Extract title
                title_elem = card.select_one("h1, h2, h3, .mat-tooltip, [class*='title']")
                title = clean_text(title_elem.get_text()) if title_elem else None
                
                if not title or len(title) < 3:
                    continue
                
                # Extract date/time
                date_elem = card.select_one("[class*='date'], .event-date, time")
                date_time = extract_date_time(date_elem.get_text()) if date_elem else "Date not specified"
                
                # Extract location
                location_elem = card.select_one("[class*='location'], [class*='venue']")
                location = clean_text(location_elem.get_text()) if location_elem else "Lebanon"
                
                # Extract event link
                link_elem = card.select_one("a")
                link = urljoin(url, link_elem['href']) if link_elem and 'href' in link_elem.attrs else ""
                
                # Extract description
                desc_elem = card.select_one("[class*='description'], p")
                description = clean_text(desc_elem.get_text()) if desc_elem else "No description"
                
                results["lebtivity_events"].append({
                    "title": title,
                    "date_time": date_time,
                    "location": location,
                    "description": description[:500],
                    "url": link
                })
            
            except Exception as e:
                print(f"      Error parsing lebtivity card: {e}")
                continue
    
    except Exception as e:
        print(f"      Error scraping lebtivity {url}: {e}")

async def scrape_ticketingbox(page, url, results):
    """Scrape ticketingboxoffice.com"""
    
    if url in results["visited_urls"]:
        return
    results["visited_urls"].add(url)
    
    print(f"  --> Scraping ticketing box: {url}")
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        
        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")
        
        if "ticketing_events" not in results:
            results["ticketing_events"] = []
        
        # Find ticketing event cards
        event_cards = soup.select("div[class*='event'], div[class*='ticket'], li[class*='event']")
        
        for card in event_cards:
            try:
                # Extract title
                title_elem = card.select_one("h2, h3, [class*='title']")
                title = clean_text(title_elem.get_text()) if title_elem else None
                
                if not title or len(title) < 3:
                    continue
                
                # Extract date/time
                date_elem = card.select_one("[class*='date'], time, .event-date")
                date_time = extract_date_time(date_elem.get_text()) if date_elem else "Date not specified"
                
                # Extract location
                location_elem = card.select_one("[class*='location'], [class*='venue'], [class*='place']")
                location = clean_text(location_elem.get_text()) if location_elem else "Lebanon"
                
                # Extract link
                link_elem = card.select_one("a")
                link = urljoin(url, link_elem['href']) if link_elem and 'href' in link_elem.attrs else ""
                
                # Extract description/details
                desc_elem = card.select_one("p, [class*='description']")
                description = clean_text(desc_elem.get_text()) if desc_elem else "No description"
                
                results["ticketing_events"].append({
                    "title": title,
                    "date_time": date_time,
                    "location": location,
                    "description": description[:500],
                    "url": link
                })
            
            except Exception as e:
                print(f"      Error parsing ticketing card: {e}")
                continue
    
    except Exception as e:
        print(f"      Error scraping ticketing box {url}: {e}")

async def study_events(browser, targets):
    """Main scraping function"""
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    page = await context.new_page()
    
    results = {
        "visited_urls": set(),
        "to_visit": [],
        "ihjoz_list": [],
        "ihjoz_details": {},
        "lebtivity_events": [],
        "ticketing_events": []
    }
    
    # Process each target site
    for target in targets:
        if "ihjoz.com" in target:
            results["to_visit"].append(target)
        elif "lebtivity.com" in target:
            await scrape_lebtivity(page, target, results)
        elif "ticketingboxoffice.com" in target:
            await scrape_ticketingbox(page, target, results)
    
    # Process list-then-detail sites (ihjoz only)
    while results["to_visit"]:
        current_url = results["to_visit"].pop(0)
        if "ihjoz.com" in current_url:
            await scrape_ihjoz(page, current_url, results)
        await asyncio.sleep(1.5)
    
    # Compile final ihjoz events
    final_ihjoz_events = []
    if results["ihjoz_list"]:
        for item in results["ihjoz_list"]:
            details = results["ihjoz_details"].get(item["url"], {})
            if details:
                final_ihjoz_events.append(details)
            else:
                final_ihjoz_events.append({
                    "title": item["title"],
                    "url": item["url"],
                    "date_time": "Details not fetched",
                    "location": "Lebanon",
                    "description": "Please visit event page for details"
                })
    
    # Save raw results
    all_events = {
        "ihjoz_events": final_ihjoz_events,
        "lebtivity_events": results["lebtivity_events"],
        "ticketing_events": results["ticketing_events"]
    }
    
    with open("outputs/lebanon_events_all.json", "w", encoding="utf-8") as f:
        json.dump(all_events, f, indent=4, ensure_ascii=False)
    
    print("\n🌍 Starting geocoding for locations...")
    
    # Create filtered version with geocoding
    filtered_events = []
    unique_locations = {}
    
    all_event_lists = [
        ("ihjoz", final_ihjoz_events),
        ("lebtivity", results["lebtivity_events"]),
        ("ticketing", results["ticketing_events"])
    ]
    
    for source_name, event_list in all_event_lists:
        for event in event_list:
            if not event.get("title") or len(event["title"]) < 2:
                continue
            
            location = event.get("location", "Lebanon")
            
            # Geocode if not cached
            if location not in unique_locations:
                lat, lon = await geocode_location(page, location)
                unique_locations[location] = {"latitude": lat, "longitude": lon}
                await asyncio.sleep(1)
            
            coords = unique_locations[location]
            
            filtered_events.append({
                "source": source_name,
                "title": event.get("title", "Untitled Event"),
                "date_time": event.get("date_time", "Date not specified"),
                "location": location,
                "latitude": coords["latitude"],
                "longitude": coords["longitude"],
                "description": event.get("description", "No description")[:500],
                "url": event.get("url", "")
            })
    
    # DEDUPLICATION
    print(f"\n🔍 Deduplicating events...")
    print(f"   Events before deduplication: {len(filtered_events)}")
    
    def normalize_for_comparison(text):
        if not text:
            return ""
        normalized = text.lower().strip()
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized
    
    def events_are_duplicate(event1, event2):
        title1 = normalize_for_comparison(event1.get("title", ""))
        title2 = normalize_for_comparison(event2.get("title", ""))
        location1 = normalize_for_comparison(event1.get("location", ""))
        location2 = normalize_for_comparison(event2.get("location", ""))
        date1 = normalize_for_comparison(event1.get("date_time", ""))
        date2 = normalize_for_comparison(event2.get("date_time", ""))
        
        return (title1 == title2 and 
                location1 == location2 and 
                date1 == date2 and
                len(title1) > 0)
    
    deduplicated_events = []
    seen_events = []
    duplicate_count = 0
    
    for event in filtered_events:
        is_duplicate = False
        for idx, seen_event in enumerate(seen_events):
            if events_are_duplicate(event, seen_event):
                is_duplicate = True
                duplicate_count += 1
                
                current_sources = deduplicated_events[idx].get("sources", [deduplicated_events[idx]["source"]])
                if event["source"] not in current_sources:
                    current_sources.append(event["source"])
                
                deduplicated_events[idx]["sources"] = current_sources
                
                if len(event.get("description", "")) > len(deduplicated_events[idx].get("description", "")):
                    deduplicated_events[idx]["description"] = event["description"]
                
                if event.get("url") and len(event.get("description", "")) > len(seen_event.get("description", "")):
                    deduplicated_events[idx]["url"] = event["url"]
                
                break
        
        if not is_duplicate:
            event["sources"] = [event["source"]]
            deduplicated_events.append(event)
            seen_events.append(event)
    
    for event in deduplicated_events:
        sources = event.get("sources", [event.get("source")])
        if len(sources) == 1:
            event["source"] = sources[0]
            event.pop("sources", None)
        else:
            event["source"] = ", ".join(sources)
            event.pop("sources", None)
    
    print(f"   Duplicates removed: {duplicate_count}")
    print(f"   Events after deduplication: {len(deduplicated_events)}")
    
    with open("outputs/lebanon_events_filtered.json", "w", encoding="utf-8") as f:
        json.dump(deduplicated_events, f, indent=4, ensure_ascii=False)
    
    print(f"\n✅ Scraping complete!")
    print(f"   - ihjoz events: {len(final_ihjoz_events)}")
    print(f"   - lebtivity events: {len(results['lebtivity_events'])}")
    print(f"   - ticketing events: {len(results['ticketing_events'])}")
    print(f"   - Total events before deduplication: {len(filtered_events)}")
    print(f"   - Total unique events after deduplication: {len(deduplicated_events)}")
    print(f"   - Unique locations geocoded: {len(unique_locations)}")
    
    await context.close()

async def main():
    targets = [
        "https://ihjoz.com/",
        "https://www.lebtivity.com/",
        "https://www.ticketingboxoffice.com/"
    ]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        await study_events(browser, targets)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

"""
Lebanese News & Holiday Scraper
Scrapes from:
  - NNA (nna-leb.gov.lb) - Lebanese national news
  - TimeAndDate - Lebanon holidays for current, previous, and next year
"""

import asyncio
import json
import re
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

async def hybrid_scraper(page, url, results):
    if url in results["visited_urls"]:
        return
    results["visited_urls"].add(url)
    
    print(f"  --> Studying: {url}")
    
    try:
        # Load the page and wait for the main content
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)

        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")
        
        # ---------------------------------------------------------
        # RULE 1: NNA Website Logic (Precise Time Extraction)
        # ---------------------------------------------------------
        if "nna-leb.gov.lb" in url:
            if "latest-news" in url:
                if "nna_list_data" not in results: results["nna_list_data"] = []
                list_items = soup.select("li.flex.flex-col")
                for li in list_items:
                    try:
                        article_link = li.select_one('a[href*="/news/"]')
                        if article_link:
                            full_link = urljoin(url, article_link['href'])
                            title = article_link.get_text(strip=True)
                            
                            results["nna_list_data"].append({
                                "url": full_link,
                                "title": title,
                                "raw_meta": li.get_text(" | ", strip=True) 
                            })
                            if full_link not in results["visited_urls"]:
                                results["to_visit"].append(full_link)
                    except: pass

            elif "/news/" in url:
                if "nna_details" not in results: results["nna_details"] = {}
                time_element = soup.select_one("div.flex.items-center.text-gray-500, main div.text-sm, .article-info")
                raw_time_text = time_element.get_text(" ", strip=True) if time_element else "N/A"
                
                final_timestamp = "N/A"
                if raw_time_text != "N/A":
                    try:
                        date_match = re.search(r"(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})", raw_time_text)
                        time_match = re.search(r"(\d{1,2}:\d{2})", raw_time_text)
                        
                        if date_match and time_match:
                            day, month, year = date_match.groups()
                            time_val = time_match.group(1)
                            clean_str = f"{day} {month} {year} {time_val}"
                            date_obj = datetime.strptime(clean_str, "%d %B %Y %H:%M")
                            final_timestamp = date_obj.strftime("%Y-%m-%d %I:%M %p")
                        else:
                            final_timestamp = raw_time_text 
                    except:
                        final_timestamp = raw_time_text

                body_div = soup.select_one("div.prose, .article-text, main article")
                paragraphs = [p.get_text(strip=True) for p in body_div.find_all('p')] if body_div else []
                
                results["nna_details"][url] = {
                    "precise_timestamp": final_timestamp,
                    "description": "\n\n".join([p for p in paragraphs if len(p) > 20])
                }
        
        # ---------------------------------------------------------
        # RULE 2: TimeAndDate Holiday Logic
        # ---------------------------------------------------------
        elif "timeanddate.com" in url:
            if "holiday_data" not in results: results["holiday_data"] = {}
            year_match = re.search(r"/(\d{4})", url)
            current_url_year = year_match.group(1) if year_match else "Unknown"
            if current_url_year not in results["holiday_data"]: results["holiday_data"][current_url_year] = []

            table = soup.select_one("#holidays-table tbody")
            if table:
                for row in table.find_all("tr"):
                    cols = row.find_all(["th", "td"])
                    if len(cols) >= 3:
                        date_str = cols[0].get_text(strip=True)
                        if not date_str or "Date" in date_str: continue
                        results["holiday_data"][current_url_year].append({
                            "date": f"{date_str}, {current_url_year}",
                            "title": cols[2].get_text(strip=True),
                            "type": cols[3].get_text(strip=True) if len(cols) > 3 else "N/A"
                        })

    except Exception as e:
        print(f"      Error at {url}: {e}")

async def study_site(browser, start_urls):
    context = await browser.new_context(user_agent="Mozilla/5.0")
    page = await context.new_page()
    
    results = {
        "visited_urls": set(),
        "to_visit": start_urls.copy(),
        "nna_list_data": [],
        "nna_details": {},
        "holiday_data": {} 
    }

    while results["to_visit"]:
        current_url = results["to_visit"].pop(0)
        await hybrid_scraper(page, current_url, results)
        await asyncio.sleep(1)

    if results["nna_list_data"]:
        final_clean_news = []
        for item in results["nna_list_data"]:
            details = results["nna_details"].get(item["url"], {})
            final_clean_news.append({
                "title": item["title"],
                "release_time": details.get("precise_timestamp", "N/A"),
                "url": item["url"],
                "description": details.get("description", "Description not found.")
            })
        with open("outputs/final_nna_news.json", "w", encoding="utf-8") as f:
            json.dump(final_clean_news, f, indent=4, ensure_ascii=False)

    if results["holiday_data"]:
        with open("outputs/yearly_holidays.json", "w", encoding="utf-8") as f:
            json.dump(results["holiday_data"], f, indent=4, ensure_ascii=False)
            
    await context.close()

async def main():
    # News targets
    nna_url = [
        "https://www.nna-leb.gov.lb/en/latest-news", 
        "https://www.nna-leb.gov.lb/en/latest-news?page=2",
        "https://www.nna-leb.gov.lb/en/latest-news?page=3"
    ]

    # DYNAMIC HOLIDAY LOGIC: Get previous, current, and next year
    current_year = datetime.now().year
    years_to_scrape = [current_year - 1, current_year, current_year + 1]
    holiday_urls = [f"https://www.timeanddate.com/holidays/lebanon/{y}" for y in years_to_scrape]
    
    print(f"📅 Dynamically generated holiday URLs for: {years_to_scrape}")
    all_targets = holiday_urls + nna_url

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        await study_site(browser, all_targets)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

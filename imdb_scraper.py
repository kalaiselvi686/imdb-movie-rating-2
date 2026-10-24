"""Scrape IMDb's Top 250 movies into a CSV file."""

import csv
import re
import sys
from pathlib import Path

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


URL = "https://www.imdb.com/chart/top/"
OUTPUT_FILE = Path(__file__).with_name("imdb_top_250.csv")
CSV_COLUMNS = ["ranking", "title", "release_year", "imdb_rating"]


def first_element(parent, selectors):
    """Return the first matching element for a list of fallback selectors."""
    for selector in selectors:
        elements = parent.find_elements(By.CSS_SELECTOR, selector)
        if elements:
            return elements[0]
    return None


def element_text(element):
    """Read visible text first, then use ARIA text when present."""
    return (
        element.text
        or element.get_attribute("textContent")
        or element.get_attribute("aria-label")
        or ""
    ).strip()


def clean_title(raw_title):
    """Remove the ranking prefix that IMDb displays before each title."""
    return re.sub(r"^\s*\d+\.\s*", "", raw_title).strip()


def extract_movie(item, position):
    """Extract one movie from an IMDb list item using fallback selectors."""
    title_element = first_element(
        item,
        [
            "h3.ipc-title__text",
            "h4.ipc-title__text",
            ".ipc-title__text",
            "a.ipc-title-link-wrapper h3",
            "a.ipc-title-link-wrapper h4",
            "h3",
            "h4",
        ],
    )
    if title_element is None:
        return None

    title = clean_title(element_text(title_element))
    item_text = " ".join(
        (item.get_attribute("innerText") or item.get_attribute("textContent") or "").split()
    )

    # IMDb currently joins the year and runtime, for example: "19942h".
    year_match = re.search(r"(?:18|19|20)\d{2}", item_text)
    rating_element = first_element(
        item,
        [
            "span.ipc-rating-star--rating",
            "span.ipc-rating-star",
            '[data-testid="ratingGroup"] span',
        ],
    )
    rating_text = element_text(rating_element) if rating_element else item_text
    # IMDb ratings are displayed with one decimal place, unlike the ranking.
    rating_match = re.search(r"(?<!\d)([0-9]\.[0-9])(?!\d)", rating_text)

    ranking_element = first_element(
        item,
        [
            '[data-testid="title-list-item-ranking"]',
            ".ipc-signpost__text",
        ],
    )
    ranking_match = (
        re.search(r"\d+", element_text(ranking_element))
        if ranking_element is not None
        else None
    )

    if not title or year_match is None or rating_match is None:
        return None

    return {
        "ranking": int(ranking_match.group(0)) if ranking_match else position,
        "title": title,
        "release_year": int(year_match.group(0)),
        "imdb_rating": float(rating_match.group(1)),
    }


def build_driver():
    """Create a Chrome driver managed automatically by webdriver-manager."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=en-US")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    # Return from navigation immediately; WebDriverWait below controls readiness.
    options.page_load_strategy = "none"
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    driver.set_page_load_timeout(45)
    return driver


def scrape_movies(driver):
    """Load IMDb and return up to 250 validated movie records."""
    print("Opening IMDb Top 250 page...")
    item_selectors = [
        "li.ipc-metadata-list-summary-item",
        '[data-testid="list-page-movie-item"]',
        "li[class*='ipc-metadata-list-summary-item']",
        "ul.ipc-metadata-list > li",
    ]

    def find_movie_items(browser):
        """Try every supported selector until a populated list is available."""
        for selector in item_selectors:
            items = browser.find_elements(By.CSS_SELECTOR, selector)
            if items:
                return items
        return False

    items = []
    last_timeout = None
    for attempt in range(1, 4):
        try:
            driver.get(URL)
        except TimeoutException as error:
            # The page can continue rendering after Chrome's navigation timeout.
            last_timeout = error
            driver.execute_script("window.stop();")

        try:
            # Scroll once so IMDb finishes rendering lazy list content.
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            items = WebDriverWait(driver, 60).until(find_movie_items)

            # IMDb may render the list in viewport-sized batches in headless Chrome.
            stable_rounds = 0
            for _ in range(40):
                previous_count = len(items)
                driver.execute_script("window.scrollBy(0, window.innerHeight);")
                try:
                    WebDriverWait(driver, 3).until(
                        lambda browser: len(find_movie_items(browser)) > previous_count
                    )
                    stable_rounds = 0
                except TimeoutException:
                    stable_rounds += 1
                items = find_movie_items(driver)
                if len(items) >= 250 or stable_rounds >= 3:
                    break

            if items:
                break
        except TimeoutException as error:
            last_timeout = error
            if attempt < 3:
                print(f"Movie list not ready; retrying ({attempt}/2)...")

    if not items:
        raise TimeoutException(
            "No supported IMDb movie-list selector matched after 3 attempts."
        ) from last_timeout

    print("Reading movie data...")
    found_count = min(len(items), 250)
    print(f"Movie items found: {found_count}")

    raw_movies = driver.execute_script(
        """
        const selectors = arguments[0];
        let elements = [];
        for (const selector of selectors) {
            elements = Array.from(document.querySelectorAll(selector));
            if (elements.length) break;
        }
        return elements.slice(0, 250).map((item, index) => {
            const title = item.querySelector(
                'h3.ipc-title__text, h4.ipc-title__text, .ipc-title__text'
            );
            const rating = item.querySelector(
                'span.ipc-rating-star--rating, span.ipc-rating-star, '
                + '[data-testid="ratingGroup"] span'
            );
            return {
                ranking: index + 1,
                title: title ? (title.textContent || '').trim() : '',
                text: (item.innerText || item.textContent || '').replace(/\\s+/g, ' '),
                rating: rating ? (rating.textContent || '').trim() : ''
            };
        });
        """,
        item_selectors,
    )

    movies = []
    for raw_movie in raw_movies:
        title = clean_title(raw_movie["title"])
        year_match = re.search(r"(?:18|19|20)\d{2}", raw_movie["text"])
        rating_match = re.search(
            r"(?<!\d)([0-9]\.[0-9])(?!\d)",
            raw_movie["rating"] or raw_movie["text"],
        )
        if title and year_match and rating_match:
            movies.append(
                {
                    "ranking": int(raw_movie["ranking"]),
                    "title": title,
                    "release_year": int(year_match.group(0)),
                    "imdb_rating": float(rating_match.group(1)),
                }
            )

    unique_movies = []
    seen_movies = set()
    for movie in movies:
        key = (
            movie["ranking"],
            movie["title"].casefold(),
            movie["release_year"],
            movie["imdb_rating"],
        )
        if key not in seen_movies:
            seen_movies.add(key)
            unique_movies.append(movie)

    if not unique_movies:
        raise RuntimeError("IMDb loaded, but no complete movie records were found.")
    if len(unique_movies) < 250:
        print(
            f"Only {len(unique_movies)} complete unique movies were extracted. "
            "IMDb may have returned an incomplete or restricted page."
        )
    return unique_movies


def save_movies(movies):
    """Validate the output shape and save a non-empty CSV."""
    data = pd.DataFrame(movies, columns=CSV_COLUMNS)
    data = data.dropna(subset=CSV_COLUMNS)
    data = data[data["title"].astype(str).str.strip().ne("")]
    if data.empty:
        raise RuntimeError("No valid movie records remain; CSV was not created.")

    if len(data) < 250:
        print(
            f"Warning: only {len(data)} complete movies are available; "
            "the CSV contains the records returned by IMDb."
        )

    data.to_csv(OUTPUT_FILE, index=False, quoting=csv.QUOTE_MINIMAL)
    print("\n" + "=" * 50)
    print(f"Saved {len(data)} movies to {OUTPUT_FILE.name}")
    print("=" * 50)
    print("\nSample data:")
    print(data.head(10).to_string(index=False))


def main():
    driver = None
    try:
        driver = build_driver()
        movies = scrape_movies(driver)
        save_movies(movies)
    except TimeoutException:
        print(
            "Error: IMDb did not show movie data before the wait timed out. "
            "Check your internet connection or IMDb availability.",
            file=sys.stderr,
        )
        return 1
    except WebDriverException as error:
        print(f"Error: Chrome WebDriver could not complete the scrape: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Error: scraping failed: {error}", file=sys.stderr)
        return 1
    finally:
        if driver is not None:
            driver.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
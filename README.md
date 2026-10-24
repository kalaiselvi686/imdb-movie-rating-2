# IMDb Movie Rating Scraper

## Project objective

This Python mini project uses Selenium to dynamically load IMDb's Top 250 Movies page and collect each movie's ranking, title, release year, and IMDb rating.

## Features

- Opens the live IMDb Top 250 page in Chrome.
- Waits for JavaScript-loaded movie data with Selenium explicit waits.
- Uses fallback selectors for small IMDb markup changes.
- Saves up to 250 validated records in `imdb_top_250.csv`.
- Prints progress messages and a sample of the saved data.
- Avoids creating an empty CSV when scraping fails.

## Technologies used

- Python
- Selenium
- pandas
- webdriver-manager
- Google Chrome and Chrome WebDriver

## Installation

Install the Python packages from the project folder:

```text
python -m pip install -r requirements.txt
```

Make sure Google Chrome is installed. `webdriver-manager` downloads a compatible ChromeDriver when the script runs.

## Run the project

```text
python imdb_scraper.py
```

The script reads the live page at <https://www.imdb.com/chart/top/> and writes the output beside the Python script.

## CSV output format

The output has exactly these columns:

```text
ranking,title,release_year,imdb_rating
```

IMDb rankings and ratings may change over time because the values are collected from the live website.
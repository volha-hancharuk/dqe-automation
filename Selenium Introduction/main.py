import time
import os

import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(BASE_DIR, "report.html")
WAIT_SECONDS = 10


class SeleniumWebDriverContextManager:
    """Opens Chrome on enter and always closes it on exit."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.driver: WebDriver | None = None

    def __enter__(self) -> WebDriver:
        options = webdriver.ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1400,1000")
        # Selenium 4.6+ downloads the matching chromedriver automatically
        self.driver = webdriver.Chrome(options=options)
        return self.driver

    def __exit__(self, exc_type, exc_value, traceback):
        if self.driver is not None:
            self.driver.quit()
        if exc_type is not None:
            print(f"Error during run: {exc_type.__name__}: {exc_value}")
        return False  # do not swallow exceptions


def element_text(element) -> str:
    # Plotly draws the report as SVG; textContent also works for rows that are
    # clipped out of view, where .text could return an empty string.
    return (element.get_attribute("textContent") or "").strip()


# ---------- Table ----------

def extract_table(driver: WebDriver, output_file: str) -> None:
    try:
        # Locator 1: XPath - wait until the table is visible
        WebDriverWait(driver, WAIT_SECONDS).until(
            EC.visibility_of_element_located((By.XPATH, "//*[@class='table']"))
        )
        # Locator 2: CLASS_NAME - table root
        table = driver.find_element(By.CLASS_NAME, "table")
        # Locator 3: CSS selector - columns inside the table
        columns = table.find_elements(By.CSS_SELECTOR, "g.y-column")
        if not columns:
            raise NoSuchElementException("No columns found in the table")

        data = {}
        for column in columns:
            # Locator 4: ID - column header
            header = element_text(column.find_element(By.ID, "header"))
            cells = column.find_elements(By.CLASS_NAME, "cell-text")
            # the header is also a cell-text element, so filter it out
            values = [element_text(c) for c in cells if element_text(c) != header]
            data[header] = values

        pd.DataFrame(data).to_csv(output_file, index=False)
        print(f"Saved {os.path.basename(output_file)} ({len(next(iter(data.values())))} rows)")

    except TimeoutException:
        print("Table did not load in time")
    except NoSuchElementException as e:
        print(f"Table element not found: {e.msg}")
    except ValueError as e:  # columns of different length
        print(f"Could not build table: {e}")


# ---------- Doughnut chart ----------

def get_slices(driver: WebDriver) -> list[tuple[str, str]]:
    doughnut = driver.find_element(By.CLASS_NAME, "pielayer")
    labels = doughnut.find_elements(By.CSS_SELECTOR, "text.slicetext[data-notex='1']")
    slices = []
    for label in labels:
        tspans = label.find_elements(By.TAG_NAME, "tspan")
        if len(tspans) >= 2:
            slices.append((element_text(tspans[0]), element_text(tspans[1])))
    return slices


def save_chart_state(driver: WebDriver, index: int) -> list[tuple[str, str]]:
    driver.save_screenshot(os.path.join(BASE_DIR, f"screenshot{index}.png"))
    slices = get_slices(driver)
    # with all filters off the chart is empty -> CSV with header only
    pd.DataFrame(
        slices, columns=["Facility Type", "Min Average Time Spent"]
    ).to_csv(os.path.join(BASE_DIR, f"doughnut{index}.csv"), index=False)
    print(f"Saved screenshot{index}.png and doughnut{index}.csv: {slices}")
    return slices


def process_doughnut(driver: WebDriver) -> None:
    try:
        WebDriverWait(driver, WAIT_SECONDS).until(
            EC.presence_of_element_located((By.CLASS_NAME, "pielayer"))
        )
        WebDriverWait(driver, WAIT_SECONDS).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".scrollbox .traces"))
        )
    except TimeoutException:
        print("Doughnut chart did not load in time")
        return

    # initial, unfiltered state
    previous = save_chart_state(driver, 0)

    legend_count = len(driver.find_elements(By.CSS_SELECTOR, ".scrollbox .traces"))
    for i in range(legend_count):
        try:
            # re-find each time: Plotly redraws the legend after every click
            legend = driver.find_element(By.CLASS_NAME, "scrollbox")
            item = legend.find_elements(By.CLASS_NAME, "traces")[i]
            print(f"Toggling filter: {element_text(item)}")
            item.click()

            # wait until the chart actually changes
            try:
                WebDriverWait(driver, WAIT_SECONDS).until(
                    lambda d: get_slices(d) != previous
                )
            except TimeoutException:
                print("Chart did not change after the click, saving anyway")
            time.sleep(0.5)  # let the redraw animation finish before screenshot

            previous = save_chart_state(driver, i + 1)

        except (NoSuchElementException, IndexError) as e:
            print(f"Filter {i} could not be applied: {e}")


if __name__ == "__main__":
    if not os.path.exists(REPORT_PATH):
        raise FileNotFoundError(f"Report not found: {REPORT_PATH}")

    with SeleniumWebDriverContextManager() as driver:
        driver.get("file://" + REPORT_PATH)
        extract_table(driver, os.path.join(BASE_DIR, "table.csv"))
        process_doughnut(driver)

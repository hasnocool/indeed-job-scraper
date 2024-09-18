**README.md**
================================

**Indeed Job Scraper**
======================

**Project Title**: Indeed Job Scraper
----------------------------------------

I built this to automate the process of scraping job listings from Indeed.com, making it easier to collect and analyze data on job postings in a specific location. This project leverages web scraping techniques using Selenium and JSON parsing with Python.

**Description**
---------------

Indeed Job Scraper is designed to fetch job listings from Indeed.com based on specified criteria (e.g., sponsorship, Chicago, IL), then parse the extracted data into a more structured format (JSON) for further analysis. The tool includes rate limiting to prevent overloading the website and ensure smooth operation.

**Features**
------------

*   **Web Scraping**: Utilizes Selenium to fetch job listings from Indeed.com.
*   **Rate Limiting**: Includes a retry mechanism with delays to avoid overwhelming the website.
*   **JSON Output**: Exports extracted data in JSON format for further processing.
*   **CSV Conversion**: Optionally, parses JSON output into a CSV file.

**Installation**
----------------

### Prerequisites

*   Python 3.x (preferably 3.9 or later)
*   Selenium WebDriver (ChromeDriver)
*   json and csv libraries

### Installation Steps

1.  Clone this repository using Git.
2.  Install required libraries using pip: `pip install selenium`
3.  Download the ChromeDriver from [here](https://chromedriver.chromium.org/downloads) and add it to your system's PATH.

**Usage**
----------

### Running the Scraper

1.  Execute the `job_scraper_with_rate_limiting.py` script.
2.  The tool will fetch job listings based on the specified criteria (sponsorship, Chicago, IL).
3.  It will parse extracted data into JSON format and save it to a file named `log_{timestamp}.json`.

### Optional CSV Conversion

1.  After running the scraper, execute the `parse_json_file_to_csv.py` script.
2.  This will convert the JSON output from the previous step into a CSV file named `job_data_extended.csv`.

**Contributing**
---------------

Contributions are welcome! If you'd like to enhance this project or add new features, please follow these steps:

1.  Fork this repository on GitHub.
2.  Make your changes in a new branch (e.g., `feature/new-feature`).
3.  Commit your changes with descriptive commit messages.
4.  Submit a pull request for review.

**License**
----------

Indeed Job Scraper is released under the [MIT License](https://opensource.org/licenses/MIT).

**Tags/Keywords**
-----------------

Indeed, web scraping, Selenium, rate limiting, JSON parsing, CSV conversion

[![Python Version](https://img.shields.io/badge/Python-3.x-green.svg)](https://www.python.org/)
[![Selenium](https://img.shields.io/badge/Selenium-4.0-green.svg)](https://selenium.dev/)
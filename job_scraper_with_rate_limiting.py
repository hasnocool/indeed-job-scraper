import logging
import json
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# ANSI escape codes for coloring text
GREEN = '\033[92m'
RED = '\033[91m'
MAGENTA = '\033[95m'
YELLOW = '\033[93m'
WHITE = '\033[97m'
RESET = '\033[0m'

# Generate unique log filenames based on the current timestamp
timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
log_filename = f"log_{timestamp}.txt"
json_filename = f"log_{timestamp}.json"

# Initialize logging
logging.basicConfig(filename=log_filename, level=logging.INFO)

# Initialize Chrome options
options = Options()
options.binary_location = "/home/hyperion/CHROME/chromium/opt/google/chrome/chrome-linux64/chrome"

# Initialize Chrome service
service = Service(executable_path="/home/hyperion/CHROME/chromium/opt/google/chrome/chrome-linux64/chromedriver")

# Initialize the Chrome WebDriver
driver = webdriver.Chrome(service=service, options=options)

# Base URL and pagination start index
base_url = "https://www.indeed.com/jobs?q=sponsorship&l=Chicago%2C+IL&vjk=c26c2a51f49fd494"
start_index = 0
jobs_per_page = 10
total_pages = 100

# Initialize JSON log
json_log = []

# Loop through pages
for i in range(total_pages):
    extraction_success = False
    retries = 0
    
    while not extraction_success and retries < 3:
        try:
            current_url = f"{base_url}&start={start_index}"
            driver.get(current_url)
            
            job_elements = driver.find_elements(By.XPATH, "//div[contains(@class, 'slider_container') and contains(@class, 'css-8xisqv') and contains(@class, 'eu4oa1w0')]")
            
            if len(job_elements) == 0:
                raise Exception("No job elements found.")
            
            for element in job_elements:
                log_entry = f"{GREEN}Tag:{RESET}{RED} {element.tag_name}{RESET}, {MAGENTA}Text:{RESET}{MAGENTA} {element.text}{RESET}, {YELLOW}Attributes:{RESET}{WHITE} {element.get_attribute('outerHTML')[:2500]}{RESET}"
                print(log_entry)
                
                # Log to text file
                logging.info(log_entry)
                
                # Log to JSON
                json_log.append({
                    'Tag': element.tag_name,
                    'Text': element.text,
                    'Attributes': element.get_attribute('outerHTML')[:2500]
                })
            
            extraction_success = True
            start_index += jobs_per_page

        except Exception as e:
            logging.error(f"An error occurred: {e}. Retrying in 60 seconds.")
            time.sleep(60)
            retries += 1

# Save JSON log
with open(json_filename, 'w') as json_file:
    json.dump(json_log, json_file, indent=4)

# Close the browser
driver.quit()

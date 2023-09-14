#!/usr/bin/python

import json
import csv
import re

def parse_job_info(job_data):
    parsed_jobs = []
    for job in job_data:
        job_info = {}
        text = job.get("Text", "")
        job_link = job.get("JobLink", "")
        
        # Extract title, company, location, salary, schedule
        title_match = re.search(r"^(.+?)\n", text)
        company_match = re.search(r"\n(.+?)\n", text)
        location_match = re.search(r"\n(.+?)(?:\n|$)", text.split("\n")[2])
        salary_match = re.search(r"(\$[\d,.]+(?: - \$[\d,.]+)?(?: a year| an hour)?)", text)
        schedule_match = re.search(r"(Full-time|Part-time|Monday to Friday|Weekend availability)", text)
        
        # Extract additional information
        job_number_match = re.search(r"Job Number: (\d+)", text)
        posted_date_match = re.search(r"Posted (\d+ days ago)", text)
        job_description_match = re.search(r"Description (.+?)(?:\n|$)", text)
        
        job_info["Title"] = title_match.group(1) if title_match else ""
        job_info["Company"] = company_match.group(1) if company_match else ""
        job_info["Location"] = location_match.group(1) if location_match else ""
        job_info["Salary"] = salary_match.group(1) if salary_match else ""
        job_info["Schedule"] = schedule_match.group(1) if schedule_match else ""
        job_info["Job Number"] = job_number_match.group(1) if job_number_match else ""
        job_info["Posted Date"] = posted_date_match.group(1) if posted_date_match else ""
        job_info["Job Description"] = job_description_match.group(1) if job_description_match else ""
        job_info["JobLink"] = job_link  # Add the job link
        
        parsed_jobs.append(job_info)
    return parsed_jobs

if __name__ == "__main__":
    # Load JSON data from file
    with open("job_data.json", "r") as f:
        job_data = json.load(f)
    
    # Parse job information
    parsed_jobs = parse_job_info(job_data)
    
    # Write to CSV
    with open("job_data_extended.csv", "w", newline="") as csvfile:
        fieldnames = ["Title", "Company", "Location", "Salary", "Schedule", "Job Number", "Posted Date", "Job Description", "JobLink"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for job in parsed_jobs:
            writer.writerow(job)

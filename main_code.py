"""
This is the main code to gather and record the bls data.
Built in Colab
"""

import requests
import pandas as pd
from datetime import datetime

BLS_API_KEY = "f68aa4d0aa9b4d2d938538c39678940c"
BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

series_ids = {
    "LNS11000000": "Civilian Labor Force",
    "LNS12000000": "Civilian Employment",
    "LNS13000000": "Civilian Unemployment",
    "LNS14000000": "Unemployment Rate",
    "CES0000000001": "Total Nonfarm Employment",
}

# api part 
def fetch_bls_data(session, series_id, start_year=2014, end_year=datetime.now().year):
    payload = {
        "seriesid": [series_id],
        "startyear": str(start_year),
        "endyear": str(end_year),
        "registrationkey": BLS_API_KEY,
    }

    response = session.post(BLS_URL, json=payload)
    response.raise_for_status()

    return response.json()["Results"]["series"][0]["data"]


def process_bls_data(data, series_name):
    
    data = [d for d in data if d["period"].startswith("M") and d["period"] != "M13"]

    df = pd.DataFrame({
        "date": [f"{d['year']}-{d['periodName']}" for d in data],
        "value": [d["value"] for d in data],
        "series_name": series_name,
    })

    df["date"] = pd.to_datetime(df["date"], format="%Y-%B")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    return df

#main
def main():
    all_data = []

    with requests.Session() as session:
        for series_id, series_name in series_ids.items():
            print(f"Fetching data for {series_name}...")
            raw_data = fetch_bls_data(session, series_id)
            all_data.append(process_bls_data(raw_data, series_name))

    combined_df = pd.concat(all_data, ignore_index=True)
    combined_df.to_csv("bls_data.csv", index=False)

    print("Data saved as bls_data.csv")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import sys
import json
import time
import subprocess
import argparse
import urllib.request
import urllib.error
import ssl
import os
from datetime import datetime, timedelta, timezone

# Fix for macOS Python SSL certificate issues (CERTIFICATE_VERIFY_FAILED)
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

def get_access_token():
    try:
        token = subprocess.check_output(['gcloud', 'auth', 'print-access-token'], stderr=subprocess.STDOUT)
        return token.decode('utf-8').strip()
    except subprocess.CalledProcessError as e:
        print(f"Error obtaining gcloud token: {e.output.decode('utf-8')}")
        sys.exit(1)

def parse_iso_time(time_str):
    try:
        # Python 3.11+ supports 'Z' in fromisoformat
        if time_str.endswith('Z'):
            time_str = time_str[:-1] + '+00:00'
        return datetime.fromisoformat(time_str)
    except ValueError:
        # Fallback for older python
        fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in time_str else "%Y-%m-%dT%H:%M:%SZ"
        if not time_str.endswith("Z"):
            time_str += "Z" # Force Z format if missing
        return datetime.strptime(time_str, fmt).replace(tzinfo=timezone.utc)

def format_iso_time(dt):
    # Format to YYYY-MM-DDTHH:MM:SS.mmmZ
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def chunk_time_range(start_str, end_str):
    start_dt = parse_iso_time(start_str)
    end_dt = parse_iso_time(end_str)
    
    if start_dt >= end_dt:
        print("Error: Start time must be before end time.")
        sys.exit(1)
        
    chunks = []
    current_start = start_dt
    
    # Use strictly 14 days as max range
    max_delta = timedelta(days=14)
    
    while current_start < end_dt:
        current_end = current_start + max_delta
        if current_end > end_dt:
            current_end = end_dt
        chunks.append({
            "start": format_iso_time(current_start),
            "end": format_iso_time(current_end)
        })
        current_start = current_end
        
    return chunks

def make_request(method, url, access_token, data=None):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    req_data = json.dumps(data).encode('utf-8') if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
        sys.exit(1)

def download_file(url, access_token, outdir, fallback_name):
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    req = urllib.request.Request(url, headers=headers, method='GET')
    
    try:
        with urllib.request.urlopen(req) as response:
            filename = response.info().get_filename()
            if not filename:
                filename = fallback_name
                
            os.makedirs(outdir, exist_ok=True)
            output_filepath = os.path.join(outdir, filename)
            
            with open(output_filepath, 'wb') as f:
                f.write(response.read())
        print(f"Successfully downloaded to {output_filepath}")
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        print(f"HTTP Error {e.code} while downloading result: {body}")
        sys.exit(1)

def run_report(org, env, start_time, end_time, display_name, manual_token=None, outdir="."):
    if manual_token:
        print("Using manually provided access token.")
        token = manual_token
    else:
        print("Obtaining gcloud access token...")
        token = get_access_token()
    
    # 1. Chunk the time range
    chunks = chunk_time_range(start_time, end_time)
    print(f"Date range split into {len(chunks)} chunk(s).")
    
    for i, chunk in enumerate(chunks):
        suffix = f"_{i+1}" if len(chunks) > 1 else ""
        current_name = f"{display_name}{suffix}"
        
        print(f"\n--- Processing job {i+1}/{len(chunks)}: {chunk['start']} to {chunk['end']} ---")
        
        # 2. Create the report job
        create_url = f"https://apigee.googleapis.com/v1/organizations/{org}/environments/{env}/securityReports"
        payload = {
            "metrics": [{"name":"bot_traffic","aggregationFunction":"sum"}],
            "dimensions": [
                "ax_resolved_client_ip",
                "bot_reason",
                "request_uri",
                "request_verb",
                "response_status_code",
                "target_host",
                "target_url",
                "useragent"
            ],
            "timeRange": chunk,
            "mimeType": "json",
            "displayName": current_name
        }
        
        print(f"Creating report job: {current_name}")
        create_resp = make_request('POST', create_url, token, data=payload)
        
        self_path = create_resp.get('self')
        if not self_path:
            print("Failed to get 'self' path from report creation response.")
            print(create_resp)
            continue
            
        status_url = f"https://apigee.googleapis.com/v1{self_path}"
        report_id = self_path.split("/")[-1]
        
        # 3. Poll for completion
        print(f"Waiting for report {report_id} to complete...")
        while True:
            status_resp = make_request('GET', status_url, token)
            state = status_resp.get('state')
            
            print(f"[{datetime.now().strftime('%X')}] Status: {state}")
            if state == 'completed':
                break
            elif state in ('failed', 'expired'):
                print(f"Report failed or expired. Status: {state}")
                break
                
            time.sleep(10)
            
        if state != 'completed':
            continue
            
        # 4. Download result
        result_path = status_resp.get('result', {}).get('self')
        if not result_path:
            print("No result path in response:")
            print(status_resp)
            continue
            
        download_url = f"https://apigee.googleapis.com/v1{result_path}"
        print(f"Downloading result for {current_name} ...")
        
        download_file(download_url, token, outdir, current_name)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create and download Apigee security reports.")
    parser.add_argument("--org", required=True, help="Apigee Organization Name (apigeex_org)")
    parser.add_argument("--env", required=True, help="Apigee Environment Name (apigeex_env)")
    parser.add_argument("--start", required=True, help="Start time (e.g., 2026-02-07T00:04:03Z)")
    parser.add_argument("--end", required=True, help="End time (e.g., 2026-03-05T00:04:03Z)")
    parser.add_argument("--name", required=True, help="Display Name (used for job name and filename)")
    parser.add_argument("--token", required=False, help="Optional manual access token (overrides gcloud default)")
    parser.add_argument("--outdir", required=False, default=".", help="Directory to save the downloaded reports")
    
    args = parser.parse_args()
    
    run_report(args.org, args.env, args.start, args.end, args.name, args.token, args.outdir)

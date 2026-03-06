# Apigee X - Advanced API Security Report Exporter

A Python utility to automatically create, poll, and download Apigee Security Reports. 

## Requirements
- Python 3.8+
- [Google Cloud CLI (`gcloud`)](https://cloud.google.com/sdk/docs/install) installed and authenticated (if not providing a manual token).

## Usage

Make the script executable:
```bash
chmod +x export_report.py
```

Run the script:
```bash
./export_report.py \
  --org my-apigee-org \
  --env my-apigee-env \
  --start 2026-02-07T00:00:00Z \
  --end 2026-03-05T00:00:00Z \
  --name my-report \
  --outdir ./reports
```

### Arguments

| Argument | Required | Description |
|---|---|---|
| `--org` | Yes | The Apigee Organization name. |
| `--env` | Yes | The Apigee Environment name. |
| `--start` | Yes | Start time in ISO 8601 format (e.g., `2026-02-07T00:00:00Z`). |
| `--end` | Yes | End time in ISO 8601 format (e.g., `2026-03-05T00:00:00Z`). |
| `--name` | Yes | The display name for the report job. Used as a fallback filename. |
| `--outdir` | No | Directory to save downloaded reports (Defaults to the current directory). |
| `--token` | No | A manual OAuth 2.0 access token (Overrides the automatic `gcloud` token retrieval). |

### Authentication Note
If you see a `401 Request had invalid authentication credentials` or `ACCESS_TOKEN_TYPE_UNSUPPORTED` error, ensure you are authenticated into a GCP account or Service Account that has the appropriate Apigee API scopes:
```bash
gcloud config set account service-account@your-project.iam.gserviceaccount.com
gcloud auth print-access-token
```

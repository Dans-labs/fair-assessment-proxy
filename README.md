# fair-assessment-proxy

> [!NOTE]
> 🚧 Work in Progress
>
> This project is not yet feature complete. The Quick Start below reflects the
> current development workflow and may change between releases.

## Quick Start (Development)
Create `docker-compose.override.yml` to expose the API on `localhost:8080` and run the assessment proxy:
```yaml
services:
  fair-assessment-proxy:
    ports:
      - "8080:8080"
```

```bash
make run
```

## Test (Development)

Submit an assessment:
```bash
curl --location 'localhost:8080/api/v1/assessments' \
--header 'Content-Type: application/json' \
--data '{
    "pid": "https://doi.org/10.1594/PANGAEA.908011",
    "mode": "public",
    "cached": false,
    "assessors": ["fuji", "fair_champion"]
}'
```

Example output:
```bash
{
    "id": "9268ba45-241b-47d5-8e8d-d32180eccc5b",
    "status": "queued",
}
```

For metadata made available through the configured OAI-PMH gateway, submit the
assessment with `"mode": "cached"`. Both FAIR Champion and F-UJI then assess the
gateway representation of the dataset metadata.

## Offline Assessment

Submit JSON-LD metadata, or a DataCite JSON API response with its metadata in
`data.attributes`, for an initial assessment of an unpublished dataset. No DOI or
public URL is required. The proxy assesses the metadata locally with the F-UJI
3.5.1 profile of the
[Local Offline Assessor for FAIR (LOAF)](https://dans-labs.github.io/local-offline-assessor-for-fair-loaf/)
and returns the result immediately without storing it.

```bash
curl --location 'localhost:8080/api/v1/assessments/' \
--header 'Content-Type: application/json' \
--data '{
  "assessors": ["offline"],
  "metadata": {
    "@context": "https://schema.org/",
    "@type": "Dataset",
    "name": "Unpublished soil measurements",
    "description": "Soil moisture observations awaiting publication.",
    "creator": {"name": "Ada Example"},
    "publisher": {"name": "DANS"},
    "dateCreated": "2026-09-01",
    "keywords": ["soil", "moisture"],
    "license": "https://creativecommons.org/licenses/by/4.0/",
    "conformsTo": "https://schema.org/Dataset"
  }
}'
```

The response's `offline` field has the same fields as a stored assessment
result. Cells that need external evidence, such as F4, A1.1, A1.2 and A2, are
`indeterminate`, and `raw` contains the complete LOAF result. Add a `pid` and
online assessors to queue online assessments in the same request.

## Metadata Retrieval

Retrieve a public JSON-LD or JSON document, for example to submit it to the
offline assessment. DOIs return schema.org JSON-LD through content negotiation.

```bash
curl --location 'localhost:8080/api/v1/retrieve?url=https%3A%2F%2Fdoi.org%2F10.5281%2Fzenodo.3243836'
```

The response contains the document unchanged, with its media type and the final
URL in `Content-Location`. Only `http` and `https` URLs on the standard ports are
retrieved, and only when the host and every redirect resolve to public addresses.
Documents are limited to 5 MB and 10 seconds. A rejected URL returns 400, a
failed retrieval returns 502, and too many requests return 429 with
`Retry-After`.

Each client can make 10 requests per minute, and at most 4 retrievals run at
once. Change these with `FAIR_PROXY_RETRIEVAL__REQUESTS_PER_MINUTE` and
`FAIR_PROXY_RETRIEVAL__MAX_CONCURRENT`. Behind a reverse proxy, set Uvicorn's
`FORWARDED_ALLOW_IPS` to its address so that clients are identified by their own
address.

## Results

Get the results of all assessors. `cells` holds the combined outcome of each
FAIR principle and the outcome per assessor. `results` holds each assessor's
scores, including each test's explanation and any practical guidance returned
by the configured FAIR Champion algorithm:
```bash
curl --location 'localhost:8080/api/v1/assessments/9268ba45-241b-47d5-8e8d-d32180eccc5b/results'
```

Get the result of one assessor, including its raw response:
```bash
curl --location 'localhost:8080/api/v1/assessments/9268ba45-241b-47d5-8e8d-d32180eccc5b/results/fuji'
```

Get latest report for a PID:
```bash
curl --location 'https://localhost:8080/api/v1/assessments/latest?pid=https%3A%2F%2Fdoi.org%2F10.1594%2FPANGAEA.908011'
```

## API Documentation

openAPI documentation is available at `localhost:8080/api/v1/docs` when the proxy is running.

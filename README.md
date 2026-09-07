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

Submit JSON-LD or DataCite JSON API `data.attributes` metadata for an initial
assessment of an unpublished dataset. No DOI or public URL is required. Checks
run locally, and results are returned immediately without being stored.

```bash
curl --location 'localhost:8080/api/v1/assessments/offline' \
--header 'Content-Type: application/json' \
--data '{
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

The same assessment is available as a Python function:

```python
from fair_assessment_proxy.offline import assess_metadata

result = assess_metadata(metadata)
```

The assessor checks F1, F2, F3, I1, I3, R1.1, R1.2, and R1.3 using the supplied
metadata. F4, I2, A1.1, A1.2, and A2 remain `unmeasured` because they need external
evidence. Missing identifiers fail F1 and F3; the other checks still run.

## Reports

Get the harmonized report, including each test's explanation and any practical
guidance returned by the configured FAIR Champion algorithm:
```bash
curl --location 'localhost:8080/api/v1/assessments/9268ba45-241b-47d5-8e8d-d32180eccc5b/report'
```

Get latest report for a PID:
```bash
curl --location 'https://localhost:8080/api/v1/assessments/latest?pid=https%3A%2F%2Fdoi.org%2F10.1594%2FPANGAEA.908011'
```

## API Documentation

openAPI documentation is available at `localhost:8080/api/v1/docs` when the proxy is running.

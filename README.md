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

## Reports

Get full report:
```bash
curl --location 'localhost:8080/api/v1/assessments/9268ba45-241b-47d5-8e8d-d32180eccc5b'
```

Get latest report for a PID:
```bash
curl --location 'https://localhost:8080/api/v1/assessments/latest?pid=https%3A%2F%2Fdoi.org%2F10.1594%2FPANGAEA.908011'
```

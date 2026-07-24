# fair-assessment-proxy

> [!NOTE]
> 🚧 Work in Progress
>
> This project is not yet feature complete. The Quick Start below reflects the
> current development workflow and may change between releases.

## Quick Start (Development)

```bash
docker compose up --build
```

## Test (Development)

Submit an assessment:
```bash
curl --location 'localhost:8080/api/v1/assessments' \
--header 'Content-Type: application/json' \
--data '{
    "pid": "https://doi.org/10.1594/PANGAEA.908011",
    "mode": "public",
    "assessors": ["fuji", "fair_champion"]
}'
```

Example output:
```bash
{
    "id": "9268ba45-241b-47d5-8e8d-d32180eccc5b",
    "status": "completed"
}
```

Get full report:
```bash
curl --location 'localhost:8080/api/v1/assessments/9268ba45-241b-47d5-8e8d-d32180eccc5b'
```

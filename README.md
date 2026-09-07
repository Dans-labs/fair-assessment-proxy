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

## Offline Assessment

Metadata can be assessed without resolving a PID or contacting an external
assessor. The endpoint accepts a JSON object and returns its result immediately;
offline assessments are not stored in the database.

Unpublished datasets do not need a DOI or public URL. Missing identifiers fail
the F1 and F3 checks but do not prevent the remaining metadata checks from running.

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

The offline assessor evaluates F1, F2, F3, I1, I3, R1.1, R1.2, and R1.3.
F4, I2, A1.1, A1.2, and A2 are reported as `unmeasured` because they require
search, vocabulary, protocol, authorization, or persistence checks outside the
supplied metadata. JSON-LD objects and DataCite JSON API `data.attributes`
responses are supported.

These are initial metadata checks, not a full schema validation or proof of FAIR
compliance. The licence check reports `pass` when an HTTP(S) URL passes basic
syntax checks, without retrieving or validating its contents. Licence text or a short identifier
such as `CC-BY-4.0` without a URL is `partial`; missing licence information is `fail`.
Unparseable URL identifiers do not stop the assessment or pass the global-identifier
check. JSON-LD graph nodes inherit the document context unless they declare their
own; this is not a full JSON-LD processor.

## Reports

Get full report:
```bash
curl --location 'localhost:8080/api/v1/assessments/9268ba45-241b-47d5-8e8d-d32180eccc5b'
```

Get latest report for a PID:
```bash
curl --location 'https://localhost:8080/api/v1/assessments/latest?pid=https%3A%2F%2Fdoi.org%2F10.1594%2FPANGAEA.908011'
```

## API Documentation

openAPI documentation is available at `localhost:8080/api/v1/docs` when the proxy is running.

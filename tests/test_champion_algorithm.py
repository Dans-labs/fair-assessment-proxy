from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from fair_assessment_proxy.models import AssessmentMode
from fair_assessment_proxy.plugins.base import AssessmentContext
from fair_assessment_proxy.plugins.fair_champion import FairChampionAssessor


class ChampionAlgorithmTest(IsolatedAsyncioTestCase):
    async def test_runs_configured_algorithm_for_cached_metadata(self):
        raw = {
            "tests": [
                {
                    "reference": "MetadataIndexed",
                    "testid": "https://example.org/test_FM_F4_M_MetaIndexed",
                }
            ],
            "test_results": {"MetadataIndexed": {"result": "pass"}},
        }
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = raw
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        assessor = FairChampionAssessor(
            "fair_champion",
            {
                "name": "FAIR Champion",
                "version": "0.5.8",
                "champion_base_url": "http://fair-champion:4567/champion",
                "algorithm": "example-algorithm",
                "metadata_gateway_base_url": "http://metadata-gateway:3000",
            },
        )

        with patch(
            "fair_assessment_proxy.plugins.fair_champion.httpx.AsyncClient",
            return_value=client,
        ):
            result = await assessor.assess(
                AssessmentContext(
                    pid="https://doi.org/10.1234/example",
                    mode=AssessmentMode.cached,
                )
            )

        client.post.assert_awaited_once_with(
            "http://fair-champion:4567/champion/assess/algorithm/d/example-algorithm",
            json={
                "guid": "http://metadata-gateway:3000/resource/doi/10.1234/example"
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual("completed", result.status)
        self.assertEqual("pass", result.normalised.f4)
        self.assertEqual(raw, result.raw)

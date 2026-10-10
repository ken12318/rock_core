import io
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from docx import Document
from PIL import Image
from unittest import skipUnless

from .analysis import summarize_results, validate_items
from .evaluation import build_evaluation
from .models import DetectionHistory


def samples(porosities, permeabilities):
    return validate_items([
        {"filename": f"core_{index}.jpg", "porosity": p, "permeability": k}
        for index, (p, k) in enumerate(zip(porosities, permeabilities), 1)
    ])


def payload(items):
    summary = summarize_results(items)
    return {
        "rock_type": "通用模型", "model_context": {"label": "通用模型", "is_demo": True},
        "is_batch": len(items) > 1, "list": items, "summary": summary,
        "evaluation": build_evaluation(summary["avg_porosity"], summary["avg_permeability"]),
    }


class AnalysisTests(SimpleTestCase):
    def test_single_sample_has_no_correlation_or_variation_claim(self):
        result = summarize_results(samples([12], [0]))
        self.assertIsNone(result["correlation"])
        self.assertIsNone(result["metrics"]["porosity"]["cv"])
        self.assertIsNone(result["metrics"]["permeability"]["cv"])
        self.assertEqual(result["outlier_indices"], [])
        self.assertIn("仅有一个样本", "".join(result["insights"]))
        json.dumps(result, allow_nan=False)

    def test_constant_values_and_zero_values_are_finite(self):
        result = summarize_results(samples([10] * 5, [0] * 5))
        self.assertIsNone(result["correlation"])
        self.assertEqual(result["metrics"]["porosity"]["cv"], 0)
        self.assertEqual(result["outlier_indices"], [])
        json.dumps(result, allow_nan=False)

    def test_statistics_and_correlation(self):
        result = summarize_results(samples([5, 10, 15], [10, 20, 30]))
        self.assertEqual(result["metrics"]["porosity"]["median"], 10)
        self.assertAlmostEqual(result["metrics"]["porosity"]["std"], 4.0825)
        self.assertEqual(result["correlation"], 1)
        self.assertEqual(sum(g["count"] for g in result["grade_distribution"]), 3)

    def test_two_samples_do_not_imply_reliable_correlation(self):
        self.assertIsNone(summarize_results(samples([5, 20], [10, 200]))["correlation"])

    def test_outliers_match_original_sample_numbers(self):
        result = summarize_results(samples([10, 10, 10, 10, 30], [4, 4, 4, 4, 4]))
        self.assertEqual(result["outlier_indices"], [5])
        self.assertEqual(result["metrics"]["permeability"]["outlier_indices"], [])

    def test_invalid_inputs_are_rejected(self):
        for items in ([], None, {}, [None], [{}], [{"porosity": float("nan"), "permeability": 2}],
                      [{"porosity": 5, "permeability": float("inf")}],
                      [{"porosity": 101, "permeability": 1}], [{"porosity": 5, "permeability": -1}]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                summarize_results(items)


class AnalysisAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="analysis-test")
        self.client.force_login(self.user)

    @patch("core_app.views.get_model_context", return_value={"label": "通用模型", "is_demo": True})
    @patch("core_app.views.get_available_rock_types", return_value=["通用模型", "砂岩"])
    @patch("core_app.views.predict_properties", side_effect=[(10, 20), (20, 100)])
    def test_prediction_returns_statistics(self, predict, available, context):
        image = io.BytesIO()
        Image.new("RGB", (20, 20)).save(image, "PNG")
        files = [SimpleUploadedFile(f"core_{i}.png", image.getvalue(), "image/png") for i in range(2)]
        response = self.client.post("/api/predict/", {"images": files})
        self.assertEqual(response.status_code, 200)
        result = response.json()["data"]
        self.assertEqual(result["summary"]["avg_porosity"], 15)
        self.assertEqual(result["summary"]["count"], 2)
        self.assertTrue(result["model_context"]["is_demo"])
        self.assertEqual(DetectionHistory.objects.count(), 2)

    def test_export_recalculates_statistics_and_keeps_demo_label(self):
        data = payload(samples([10, 20], [20, 100]))
        data["summary"]["count"] = 999
        response = self.client.post("/api/export/docx/", data=json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        doc = Document(io.BytesIO(b"".join(response.streaming_content)))
        text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("样本数量：2 张", text)
        self.assertIn("演示模型", text)
        self.assertIn("四、图表分析总结", text)
        self.assertNotIn("999", text)

    def test_export_rejects_empty_or_invalid_payload(self):
        for body in ("{}", "[]", "not-json", '{"list":[{}]}'):
            with self.subTest(body=body):
                response = self.client.post("/api/export/docx/", data=body, content_type="application/json")
                self.assertEqual(response.status_code, 400)

    def test_report_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.post("/api/export/docx/", {}).status_code, 302)


@skipUnless(os.getenv("ROCK_BROWSER_TEST") == "1", "Optional Playwright browser regression")
class DashboardBrowserTests(StaticLiveServerTestCase):
    @patch("core_app.views.get_available_rock_types", return_value=["通用模型", "砂岩"])
    def test_dashboard_browser(self, available):
        user = User.objects.create_user(username="browser-test")
        self.client.force_login(user)
        fixtures = [payload(samples([8, 9, 10, 11, 12, 30], [2, 3, 4, 5, 6, 300])),
                    payload(samples([12], [0])), payload(samples([10] * 5, [10] * 5))]
        script = Path(settings.BASE_DIR) / "tests" / "dashboard.browser.cjs"
        result = subprocess.run(
            ["node", str(script), self.live_server_url, self.client.cookies["sessionid"].value, json.dumps(fixtures)],
            capture_output=True, text=True, encoding="utf-8", timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout)

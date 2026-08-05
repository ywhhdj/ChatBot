import unittest
from pathlib import Path
from fastapi.testclient import TestClient
import sys
import os
import time

# Add the project root to Python path to allow imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


from src_py.modules.ui.web_app import get_web_app,create_webapp
app = create_webapp()
# APP_JSON = Path(__file__).resolve().parents[1] / "app.json"


class WebApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # cls.original_app_json = APP_JSON.read_text(encoding="utf-8")

    # @classmethod
    # def tearDownClass(cls):
    #     APP_JSON.write_text(cls.original_app_json, encoding="utf-8")

    def test_health(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["status"])
        self.assertEqual(body["data"]["status"], "healthy")

    def test_config_system_roundtrip(self):
        payload = {"log": {"level": "DEBUG"}, "network": {"timeout": 30}}
        put_res = self.client.put("/config/system", json=payload)
        self.assertEqual(put_res.status_code, 200)
        self.assertTrue(put_res.json()["status"])

        get_res = self.client.get("/config/system")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["data"], payload)

    def test_config_advanced_roundtrip(self):
        payload = {
            "install_components": ["nodejs", "ffmpeg"],
            "code_highlight": {"enabled": True, "theme": "github-dark"},
            "extra": {"x": 1},
        }
        put_res = self.client.put("/config/advanced", json=payload)
        self.assertEqual(put_res.status_code, 200)
        self.assertTrue(put_res.json()["status"])

        get_res = self.client.get("/config/advanced")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["data"], payload)

    def test_logger_flow(self):
        levels_res = self.client.get("/logger/levels")
        self.assertEqual(levels_res.status_code, 200)
        self.assertTrue(levels_res.json()["status"])

        push_res = self.client.post(
            "/logger/push",
            json={"level": "INFO", "logger": "test_web_api", "message": "hello"},
        )
        self.assertEqual(push_res.status_code, 200)
        self.assertTrue(push_res.json()["status"])

        records_res = self.client.get("/logger/records")
        self.assertEqual(records_res.status_code, 200)
        body = records_res.json()
        self.assertTrue(body["status"])
        records = body["data"]
        self.assertTrue(any("hello" in item.get("message", "") for item in records))

        clear_res = self.client.delete("/logger/records")
        self.assertEqual(clear_res.status_code, 200)
        self.assertTrue(clear_res.json()["status"])

if __name__ == "__main__":
    unittest.main()

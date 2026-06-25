"""Tests for the iPhone Backup Manager web application."""
import json
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import app as app_module
from app import BACKUP_DIR, app as flask_app


class TestHelpers(unittest.TestCase):
    """Unit tests for internal helper functions."""

    # ------------------------------------------------------------------
    # _list_devices
    # ------------------------------------------------------------------

    @patch("app.subprocess.run")
    def test_list_devices_returns_devices(self, mock_run):
        udid = "abc123def456"
        # First call: idevice_id -l
        mock_run.return_value = MagicMock(stdout=f"{udid}\n", returncode=0)
        devices = app_module._list_devices()
        self.assertTrue(any(d["udid"] == udid for d in devices))

    @patch("app.subprocess.run", side_effect=FileNotFoundError)
    def test_list_devices_missing_tool(self, _mock):
        devices = app_module._list_devices()
        self.assertEqual(devices, [])

    # ------------------------------------------------------------------
    # _device_name
    # ------------------------------------------------------------------

    @patch("app.subprocess.run")
    def test_device_name_returns_name(self, mock_run):
        mock_run.return_value = MagicMock(stdout="My iPhone\n", returncode=0)
        name = app_module._device_name("udid-abc")
        self.assertEqual(name, "My iPhone")

    @patch("app.subprocess.run", side_effect=FileNotFoundError)
    def test_device_name_fallback_to_udid(self, _mock):
        name = app_module._device_name("fallback-udid")
        self.assertEqual(name, "fallback-udid")

    # ------------------------------------------------------------------
    # _device_info
    # ------------------------------------------------------------------

    @patch("app.subprocess.run")
    def test_device_info_returns_dict(self, mock_run):
        mock_run.return_value = MagicMock(stdout="iPhone14,2\n", returncode=0)
        info = app_module._device_info("some-udid")
        self.assertIn("DeviceName", info)
        self.assertIn("ProductType", info)

    @patch("app.subprocess.run", side_effect=FileNotFoundError)
    def test_device_info_na_when_tool_missing(self, _mock):
        info = app_module._device_info("some-udid")
        for v in info.values():
            self.assertEqual(v, "N/A")

    # ------------------------------------------------------------------
    # _list_backups
    # ------------------------------------------------------------------

    def test_list_backups_empty(self):
        # Use a non-existent path to ensure empty result
        original = app_module.BACKUP_DIR
        app_module.BACKUP_DIR = Path("/tmp/nonexistent_backup_dir_xyz")
        try:
            backups = app_module._list_backups()
            self.assertEqual(backups, [])
        finally:
            app_module.BACKUP_DIR = original

    def test_list_backups_with_entries(self, tmp_path=None):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / "udid-1111").mkdir()
            (p / "udid-2222").mkdir()
            original = app_module.BACKUP_DIR
            app_module.BACKUP_DIR = p
            try:
                backups = app_module._list_backups()
                udids = [b["udid"] for b in backups]
                self.assertIn("udid-1111", udids)
                self.assertIn("udid-2222", udids)
            finally:
                app_module.BACKUP_DIR = original

    # ------------------------------------------------------------------
    # _start_job / _run_command
    # ------------------------------------------------------------------

    def test_start_job_records_job(self):
        with patch("app.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
            job_id = app_module._start_job(["echo", "hello"], "test job")
            self.assertIn(job_id, app_module.jobs)
            # Wait briefly for thread to finish
            for _ in range(20):
                time.sleep(0.1)
                if app_module.jobs[job_id]["status"] in ("success", "failed"):
                    break
            self.assertEqual(app_module.jobs[job_id]["status"], "success")

    def test_run_command_records_failure(self):
        with patch("app.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="err", returncode=1)
            job_id = app_module._start_job(["false"], "failing job")
            for _ in range(20):
                time.sleep(0.1)
                if app_module.jobs[job_id]["status"] in ("success", "failed"):
                    break
            self.assertEqual(app_module.jobs[job_id]["status"], "failed")

    def test_run_command_records_missing_tool(self):
        with patch("app.subprocess.run", side_effect=FileNotFoundError("no tool")):
            job_id = app_module._start_job(["no_such_tool"], "missing tool job")
            for _ in range(20):
                time.sleep(0.1)
                if app_module.jobs[job_id]["status"] in ("success", "failed"):
                    break
            self.assertEqual(app_module.jobs[job_id]["status"], "failed")
            self.assertIn("Executable not found", app_module.jobs[job_id]["error"])


class TestRoutes(unittest.TestCase):
    """Integration tests for Flask routes."""

    def setUp(self):
        flask_app.config["TESTING"] = True
        self.client = flask_app.test_client()
        # Clear jobs between tests
        app_module.jobs.clear()

    # ------------------------------------------------------------------
    # GET /
    # ------------------------------------------------------------------

    @patch("app._list_devices", return_value=[])
    @patch("app._list_backups", return_value=[])
    def test_index_ok(self, _b, _d):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Dashboard", resp.data)

    @patch("app._list_devices", return_value=[{"udid": "abc123", "name": "My iPhone"}])
    @patch("app._list_backups", return_value=[])
    def test_index_shows_device(self, _b, _d):
        resp = self.client.get("/")
        self.assertIn(b"My iPhone", resp.data)

    # ------------------------------------------------------------------
    # GET /devices
    # ------------------------------------------------------------------

    @patch("app._list_devices", return_value=[{"udid": "abc123", "name": "iPhone"}])
    def test_devices_json(self, _mock):
        resp = self.client.get("/devices")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data[0]["udid"], "abc123")

    # ------------------------------------------------------------------
    # GET /device/<udid>
    # ------------------------------------------------------------------

    @patch("app._device_info", return_value={"DeviceName": "My Phone", "ProductType": "iPhone14,2"})
    def test_device_info_page(self, _mock):
        resp = self.client.get("/device/abc123")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"My Phone", resp.data)

    # ------------------------------------------------------------------
    # POST /backup
    # ------------------------------------------------------------------

    @patch("app._start_job", return_value="job-123")
    def test_backup_post_redirects(self, mock_job):
        resp = self.client.post("/backup", data={"udid": "abc123"})
        self.assertIn(resp.status_code, (301, 302))
        mock_job.assert_called_once()
        args = mock_job.call_args[0][0]
        self.assertIn("idevicebackup2", args)
        self.assertIn("backup", args)

    def test_backup_post_no_udid(self):
        resp = self.client.post("/backup", data={})
        self.assertEqual(resp.status_code, 400)

    # ------------------------------------------------------------------
    # POST /restore
    # ------------------------------------------------------------------

    def test_restore_post_no_udid(self):
        resp = self.client.post("/restore", data={})
        self.assertEqual(resp.status_code, 400)

    def test_restore_post_no_backup(self):
        resp = self.client.post("/restore", data={"udid": "no-backup-for-this"})
        self.assertEqual(resp.status_code, 404)

    @patch("app._start_job", return_value="job-456")
    def test_restore_post_with_backup(self, mock_job, tmp_path=None):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            udid = "test-udid-restore"
            backup_path = Path(tmpdir) / udid
            backup_path.mkdir()
            original = app_module.BACKUP_DIR
            app_module.BACKUP_DIR = Path(tmpdir)
            try:
                resp = self.client.post("/restore", data={"udid": udid})
                self.assertIn(resp.status_code, (301, 302))
                mock_job.assert_called_once()
                args = mock_job.call_args[0][0]
                self.assertIn("idevicebackup2", args)
                self.assertIn("restore", args)
            finally:
                app_module.BACKUP_DIR = original

    # ------------------------------------------------------------------
    # GET /jobs
    # ------------------------------------------------------------------

    def test_job_list_empty(self):
        resp = self.client.get("/jobs")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Jobs", resp.data)

    # ------------------------------------------------------------------
    # GET /jobs/<job_id>  &  GET /api/jobs/<job_id>
    # ------------------------------------------------------------------

    def test_job_status_not_found(self):
        resp = self.client.get("/jobs/nonexistent-id")
        self.assertEqual(resp.status_code, 404)

    def test_api_job_status_not_found(self):
        resp = self.client.get("/api/jobs/nonexistent-id")
        self.assertEqual(resp.status_code, 404)
        data = json.loads(resp.data)
        self.assertIn("error", data)

    def test_job_status_ok(self):
        app_module.jobs["j1"] = {
            "id": "j1",
            "label": "Test Job",
            "status": "success",
            "output": "done",
            "error": "",
            "returncode": 0,
            "started_at": "2024-01-01T00:00:00",
            "finished_at": "2024-01-01T00:01:00",
        }
        resp = self.client.get("/jobs/j1")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Test Job", resp.data)

    def test_api_job_status_ok(self):
        app_module.jobs["j2"] = {
            "id": "j2",
            "label": "API Job",
            "status": "running",
            "output": "",
            "error": "",
            "returncode": None,
            "started_at": "2024-01-01T00:00:00",
            "finished_at": None,
        }
        resp = self.client.get("/api/jobs/j2")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "running")


if __name__ == "__main__":
    unittest.main()

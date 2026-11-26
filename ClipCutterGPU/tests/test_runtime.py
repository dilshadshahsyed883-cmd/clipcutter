"""CPU-only regression coverage for the real GPU startup probe contract."""
import subprocess
import unittest
from unittest.mock import patch
from worker import runtime


class EncoderProbeTests(unittest.TestCase):
    @patch("worker.runtime.subprocess.run")
    def test_success_both_codecs_at_supported_resolution(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        status = runtime.verify_encoders("auto")
        self.assertEqual(status, {
            "provider": "CUDAExecutionProvider", "nvenc_test_passed": True,
            "hevc_nvenc_test_passed": True, "h264_nvenc_test_passed": True,
            "encoder_policy": "auto"})
        self.assertEqual(run.call_count, 2)
        for call, codec in zip(run.call_args_list, ("hevc_nvenc", "h264_nvenc")):
            command = call.args[0]
            self.assertEqual(command[command.index("-i") + 1], "color=size=1280x720:rate=25")
            self.assertEqual(command[command.index("-frames:v") + 1], "25")
            self.assertEqual(command[command.index("-c:v") + 1], codec)
            self.assertEqual(call.kwargs["timeout"], 25)
            self.assertTrue(call.kwargs["capture_output"])
            self.assertTrue(call.kwargs["text"])

    @patch("worker.runtime.subprocess.run")
    def test_failure_logged_and_auto_remains_available(self, run):
        run.side_effect = [
            subprocess.CompletedProcess([], 234, "", "Frame dimensions are less than minimum"),
            subprocess.CompletedProcess([], 0, "", "")]
        with self.assertLogs("worker.runtime", level="WARNING") as log:
            status = runtime.verify_encoders("auto")
        self.assertFalse(status["nvenc_test_passed"])
        self.assertFalse(status["hevc_nvenc_test_passed"])
        self.assertTrue(status["h264_nvenc_test_passed"])
        self.assertIn("234", log.output[0])
        self.assertIn("Frame dimensions", log.output[0])

    @patch("worker.runtime.probe_nvenc", side_effect=[False, True])
    def test_strict_requires_hevc(self, probe):
        with self.assertRaisesRegex(RuntimeError, "hevc_nvenc"):
            runtime.verify_encoders("nvenc")

    @patch("worker.runtime.probe_nvenc", side_effect=[True, False])
    def test_h264_failure_does_not_disable_hevc(self, probe):
        status = runtime.verify_encoders("nvenc")
        self.assertTrue(status["nvenc_test_passed"])
        self.assertFalse(status["h264_nvenc_test_passed"])

    @patch("worker.runtime.probe_nvenc", return_value=False)
    def test_cpu_policy_and_invalid_policy(self, probe):
        self.assertFalse(runtime.verify_encoders("cpu")["nvenc_test_passed"])
        self.assertEqual(probe.call_count, 2)
        with self.assertRaisesRegex(RuntimeError, "Invalid encoder policy"):
            runtime.verify_encoders("invalid")
        self.assertEqual(probe.call_count, 2)

    @patch("worker.runtime.subprocess.run")
    def test_timeout_and_missing_binary_logged(self, run):
        for error in (subprocess.TimeoutExpired("ffmpeg", 25), FileNotFoundError("ffmpeg")):
            run.side_effect = error
            with self.assertLogs("worker.runtime", level="WARNING"):
                self.assertFalse(runtime.probe_nvenc("hevc_nvenc"))


if __name__ == "__main__":
    unittest.main()

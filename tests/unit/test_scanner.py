"""Unit tests for app/scanner/windows.py (docs/SCAN_PLAN.md §9).

The real WIA layer was proven on hardware by spike_scan.py (S1: the L3210
plugged AND unplugged). These tests pin the logic around it: detection
never raises, degrades to [] on any failure, and only Type==1 entries
count as scanners. Same fake-module pattern as test_printer_windows.py.
"""

import sys

from app.scanner import windows as scanner_windows


class TestListScanDevices:
    def test_finds_a_scanner(self, fake_win32com):
        fake_win32com.add_device(name="EPSON L3210 Series", device_id="wia-l3210")
        devices = scanner_windows.list_scan_devices()
        assert [(d.name, d.id) for d in devices] == [
            ("EPSON L3210 Series", "wia-l3210")
        ]

    def test_no_devices_means_empty_list(self, fake_win32com):
        assert scanner_windows.list_scan_devices() == []

    def test_devices_without_scanners_mean_empty_list(self, fake_win32com):
        # A webcam (Type 2) must not pose as a scanner (SCAN_PLAN §3.2).
        fake_win32com.add_device(name="Webcam", wia_type=2)
        assert scanner_windows.list_scan_devices() == []

    def test_only_scanner_type_entries_are_kept(self, fake_win32com):
        fake_win32com.add_device(name="Webcam", wia_type=2)
        fake_win32com.add_device(name="EPSON L3210 Series")
        devices = scanner_windows.list_scan_devices()
        assert [d.name for d in devices] == ["EPSON L3210 Series"]

    def test_com_failure_degrades_to_empty_even_with_a_scanner(
        self, fake_win32com
    ):
        fake_win32com.add_device()
        fake_win32com.fail_dispatch(RuntimeError("WIA service disabled"))
        assert scanner_windows.list_scan_devices() == []

    def test_missing_pywin32_degrades_to_empty(self, monkeypatch):
        # None in sys.modules makes the import itself raise ImportError.
        monkeypatch.setitem(sys.modules, "win32com", None)
        assert scanner_windows.list_scan_devices() == []

    def test_unreadable_entry_does_not_hide_healthy_scanners(self, fake_win32com):
        class Broken:
            @property
            def Type(self):
                raise RuntimeError("COM boom")

        fake_win32com.infos.items.append(Broken())
        fake_win32com.add_device(name="EPSON L3210 Series")
        devices = scanner_windows.list_scan_devices()
        assert [d.name for d in devices] == ["EPSON L3210 Series"]

    def test_unreadable_name_falls_back_to_empty_string(self, fake_win32com):
        fake_win32com.add_device(no_name=True)
        assert scanner_windows.list_scan_devices()[0].name == ""

    def test_device_id_is_stringified(self, fake_win32com):
        fake_win32com.add_device(device_id=12345)
        assert scanner_windows.list_scan_devices()[0].id == "12345"


class TestAvailability:
    def test_available_with_a_scanner(self, fake_win32com):
        fake_win32com.add_device()
        assert scanner_windows.scan_available() is True

    def test_not_available_without_one(self, fake_win32com):
        assert scanner_windows.scan_available() is False

    def test_supported_needs_the_flag_and_the_hardware(
        self, fake_win32com, monkeypatch
    ):
        fake_win32com.add_device()
        monkeypatch.setattr(scanner_windows, "ENABLE_SCAN", True)
        assert scanner_windows.scanning_supported() is True
        monkeypatch.setattr(scanner_windows, "ENABLE_SCAN", False)
        assert scanner_windows.scanning_supported() is False

    def test_supported_needs_hardware_even_when_enabled(
        self, fake_win32com, monkeypatch
    ):
        monkeypatch.setattr(scanner_windows, "ENABLE_SCAN", True)
        assert scanner_windows.scanning_supported() is False

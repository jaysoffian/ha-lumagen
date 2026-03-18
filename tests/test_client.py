"""Tests for Lumagen RS-232 client response parsing."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.ha_lumagen.client import (
    ASPECT_COMMANDS,
    ASPECT_RATIO_NAMES,
    REMOTE_COMMANDS,
    LumagenClient,
    LumagenState,
    _aspect_name,
    _handle_device_id,
    _handle_full_info,
    _handle_input_info,
    _handle_power,
    _safe_int,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> LumagenClient:
    """Create a LumagenClient without connecting."""
    return LumagenClient()


def _make_i24_fields(
    *,
    mode: str = "1",
    vrate: str = "060",
    vres: str = "2160",
    src_3d: str = "0",
    input_cfg: str = "0",
    raster_aspect: str = "178",
    content_aspect: str = "240",
    nls: str = "-",
    out_3d: str = "0",
    outputs_on: str = "0003",
    cms: str = "0",
    style: str = "0",
    out_vrate: str = "060",
    out_vres: str = "2160",
    out_aspect: str = "178",
    # v2+
    out_colorspace: str | None = "1",
    dynamic_range: str | None = "0",
    src_mode: str | None = "p",
    out_mode: str | None = "P",
    # v3+
    logical_input: str | None = "01",
    physical_input: str | None = "03",
    # v4+
    detected_raster: str | None = "178",
    detected_content: str | None = "240",
    # v5
    input_memory: str | None = None,
    power_status: str | None = None,
) -> list[str]:
    """Build an I24/I25 field list with sensible defaults."""
    fields = [
        mode,
        vrate,
        vres,
        src_3d,
        input_cfg,
        raster_aspect,
        content_aspect,
        nls,
        out_3d,
        outputs_on,
        cms,
        style,
        out_vrate,
        out_vres,
        out_aspect,
    ]
    if out_colorspace is not None:
        fields.extend(
            f
            for f in (out_colorspace, dynamic_range, src_mode, out_mode)
            if f is not None
        )
    if logical_input is not None:
        fields.extend(f for f in (logical_input, physical_input) if f is not None)
    if detected_raster is not None:
        fields.extend(f for f in (detected_raster, detected_content) if f is not None)
    if input_memory is not None:
        fields.append(input_memory)
    if power_status is not None:
        fields.append(power_status)
    return fields


# ---------------------------------------------------------------------------
# _safe_int
# ---------------------------------------------------------------------------


class TestSafeInt:
    def test_valid(self):
        assert _safe_int("42") == 42

    def test_zero(self):
        assert _safe_int("0") == 0

    def test_negative(self):
        assert _safe_int("-1") == -1

    def test_invalid(self):
        assert _safe_int("abc") is None

    def test_empty(self):
        assert _safe_int("") is None


# ---------------------------------------------------------------------------
# _aspect_name
# ---------------------------------------------------------------------------


class TestAspectName:
    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            ("133", "1.33"),
            ("178", "1.78"),
            ("185", "1.85"),
            ("190", "1.90"),
            ("200", "2.00"),
            ("210", "2.10"),
            ("220", "2.20"),
            ("235", "2.35"),
            ("240", "2.40"),
            ("255", "2.55"),
            ("276", "2.76"),
        ],
    )
    def test_known_aspects(self, code: str, expected: str):
        assert _aspect_name(code) == expected

    def test_unknown_positive(self):
        """Unknown positive code falls back to decimal formatting."""
        assert _aspect_name("166") == "1.66"

    def test_zero(self):
        assert _aspect_name("0") is None

    def test_non_numeric(self):
        assert _aspect_name("abc") is None

    def test_empty(self):
        assert _aspect_name("") is None


# ---------------------------------------------------------------------------
# _handle_device_id (S01)
# ---------------------------------------------------------------------------


class TestHandleDeviceId:
    def test_parse(self):
        state = LumagenState()
        # Example from ref: !S01,RadianceXD,102308,1009,745
        fields = ["RadiancePro", "102308", "1009", "745"]
        _handle_device_id(state, fields)
        assert state._changed
        assert state.model_name == "RadiancePro"
        assert state.software_revision == "102308"
        assert state.model_number == "1009"
        assert state.serial_number == "745"

    def test_no_change(self):
        state = LumagenState(
            model_name="RadiancePro",
            software_revision="102308",
            model_number="1009",
            serial_number="745",
        )
        state.clear_changed()
        fields = ["RadiancePro", "102308", "1009", "745"]
        _handle_device_id(state, fields)
        assert not state._changed

    def test_too_few_fields(self):
        state = LumagenState()
        state.clear_changed()
        _handle_device_id(state, ["RadiancePro", "102308"])
        assert not state._changed
        assert state.model_name is None


# ---------------------------------------------------------------------------
# _handle_power (S02)
# ---------------------------------------------------------------------------


class TestHandlePower:
    def test_active(self):
        state = LumagenState()
        _handle_power(state, ["1"])
        assert state._changed
        assert state.power == "on"

    def test_standby(self):
        state = LumagenState()
        _handle_power(state, ["0"])
        assert state._changed
        assert state.power == "off"

    def test_unknown_value_treated_as_standby(self):
        state = LumagenState()
        _handle_power(state, ["2"])
        assert state._changed
        assert state.power == "off"

    def test_empty_fields(self):
        state = LumagenState()
        state.clear_changed()
        _handle_power(state, [])
        assert not state._changed

    def test_no_change(self):
        state = LumagenState(power="on")
        state.clear_changed()
        _handle_power(state, ["1"])
        assert not state._changed


# ---------------------------------------------------------------------------
# _handle_input_info (I00)
# ---------------------------------------------------------------------------


class TestHandleInputInfo:
    def test_parse(self):
        state = LumagenState()
        # !I00,3,A,5
        fields = ["3", "A", "5"]
        _handle_input_info(state, fields)
        assert state._changed
        assert state.logical_input == 3
        assert state.input_memory == "A"
        assert state.physical_input == 5

    def test_too_few_fields(self):
        state = LumagenState()
        state.clear_changed()
        _handle_input_info(state, ["3", "A"])
        assert not state._changed

    def test_no_change(self):
        state = LumagenState(logical_input=3, input_memory="A", physical_input=5)
        state.clear_changed()
        _handle_input_info(state, ["3", "A", "5"])
        assert not state._changed


# ---------------------------------------------------------------------------
# _handle_full_info (I21/I22/I23/I24)
# ---------------------------------------------------------------------------


class TestHandleFullInfo:
    def test_v1_fields(self):
        """15 fields — only v1 data."""
        fields = _make_i24_fields(
            out_colorspace=None,
            logical_input=None,
            detected_raster=None,
        )
        assert len(fields) == 15
        state = LumagenState()
        _handle_full_info(state, fields)
        assert state._changed
        assert state.source_vertical_rate == 60
        assert state.source_vertical_resolution == 2160
        assert state.input_config_number == 0
        assert state.source_raster_aspect == "1.78"
        assert state.source_content_aspect == "2.40"
        assert state.nls_active is False
        assert state.output_cms == 0
        assert state.output_style == 0
        assert state.output_vertical_rate == 60
        assert state.output_vertical_resolution == 2160
        assert state.output_aspect == "1.78"
        # v2+ fields should be untouched
        assert state.output_colorspace is None
        assert state.source_dynamic_range is None

    def test_v2_fields(self):
        """19 fields — v1 + v2."""
        fields = _make_i24_fields(
            logical_input=None,
            detected_raster=None,
            out_colorspace="2",
            dynamic_range="1",
            src_mode="p",
        )
        assert len(fields) == 19
        state = LumagenState()
        _handle_full_info(state, fields)
        assert state._changed
        assert state.output_colorspace == "BT.2020"
        assert state.source_dynamic_range == "HDR"
        assert state.source_mode == "Progressive"
        # v3+ should be untouched
        assert state.logical_input is None

    def test_v3_fields(self):
        """21 fields — v1 + v2 + v3."""
        fields = _make_i24_fields(
            detected_raster=None,
            logical_input="05",
            physical_input="07",
        )
        assert len(fields) == 21
        state = LumagenState()
        _handle_full_info(state, fields)
        assert state._changed
        assert state.logical_input == 5
        assert state.physical_input == 7
        # v4 should be untouched
        assert state.detected_raster_aspect is None

    def test_v4_fields(self):
        """23 fields — full v4."""
        fields = _make_i24_fields(
            detected_raster="178",
            detected_content="240",
        )
        assert len(fields) == 23
        state = LumagenState()
        _handle_full_info(state, fields)
        assert state._changed
        assert state.detected_raster_aspect == "1.78"
        assert state.detected_content_aspect == "2.40"

    def test_v5_fields(self):
        """25 fields — full v5 (input memory + power)."""
        fields = _make_i24_fields(input_memory="B", power_status="1")
        assert len(fields) == 25
        state = LumagenState()
        _handle_full_info(state, fields)
        assert state._changed
        assert state.input_memory == "B"
        assert state.power == "on"

    def test_v5_power_off(self):
        """v5 power status field: 0 = off."""
        fields = _make_i24_fields(input_memory="A", power_status="0")
        state = LumagenState()
        _handle_full_info(state, fields)
        assert state.power == "off"

    def test_nls_active(self):
        fields = _make_i24_fields(nls="N")
        state = LumagenState()
        _handle_full_info(state, fields)
        assert state.nls_active is True

    def test_interlaced_source(self):
        fields = _make_i24_fields(src_mode="i")
        state = LumagenState()
        _handle_full_info(state, fields)
        assert state.source_mode == "Interlaced"

    def test_no_input_source_mode(self):
        fields = _make_i24_fields(src_mode="-")
        state = LumagenState()
        _handle_full_info(state, fields)
        assert state.source_mode is None

    def test_sdr(self):
        fields = _make_i24_fields(dynamic_range="0")
        state = LumagenState()
        _handle_full_info(state, fields)
        assert state.source_dynamic_range == "SDR"

    def test_hdr(self):
        fields = _make_i24_fields(dynamic_range="1")
        state = LumagenState()
        _handle_full_info(state, fields)
        assert state.source_dynamic_range == "HDR"

    def test_all_colorspaces(self):
        for code, name in [
            ("0", "BT.601"),
            ("1", "BT.709"),
            ("2", "BT.2020"),
            ("3", "BT.2100"),
        ]:
            fields = _make_i24_fields(out_colorspace=code)
            state = LumagenState()
            _handle_full_info(state, fields)
            assert state.output_colorspace == name

    def test_too_few_fields(self):
        state = LumagenState()
        state.clear_changed()
        _handle_full_info(state, ["1"] * 10)
        assert not state._changed

    def test_no_change(self):
        fields = _make_i24_fields()
        state = LumagenState()
        _handle_full_info(state, fields)
        state.clear_changed()
        _handle_full_info(state, fields)
        assert not state._changed

    def test_extra_fields_tolerated(self):
        """Future firmware may append additional fields."""
        fields = [
            *_make_i24_fields(input_memory="A", power_status="1"),
            "extra1",
            "extra2",
        ]
        state = LumagenState()
        _handle_full_info(state, fields)
        assert state._changed
        assert state.power == "on"


# ---------------------------------------------------------------------------
# _process_line — integration tests via LumagenClient
# ---------------------------------------------------------------------------


class TestProcessLine:
    """Test _process_line with realistic echoed lines."""

    def setup_method(self):
        self.client = _make_client()
        self.state_changes = 0
        self.client._on_state_changed = lambda: setattr(
            self, "state_changes", self.state_changes + 1
        )

    # -- Power sentinels ----------------------------------------------------

    def test_power_up_complete(self):
        self.client._process_line("Power-up complete.")
        assert self.client.state.power == "on"
        assert self.state_changes == 1

    def test_power_off(self):
        self.client._process_line("POWER OFF.")
        assert self.client.state.power == "off"
        assert self.state_changes == 1

    def test_power_up_no_duplicate_notify(self):
        self.client.state.power = "on"
        self.client.state.clear_changed()
        self.client._process_line("Power-up complete.")
        assert self.state_changes == 0

    # -- Alive (S00) -------------------------------------------------------

    def test_alive_response(self):
        self.client._process_line("ZQS00!S00,Ok")
        assert self.state_changes == 0  # alive is not a state change

    # -- S01 device ID with echo -------------------------------------------

    def test_s01_with_echo(self):
        self.client._process_line("ZQS01!S01,RadiancePro,102308,1009,745")
        s = self.client.state
        assert s.model_name == "RadiancePro"
        assert s.software_revision == "102308"
        assert s.model_number == "1009"
        assert s.serial_number == "745"
        assert self.state_changes == 1

    # -- S02 power with echo -----------------------------------------------

    def test_s02_active(self):
        self.client._process_line("ZQS02!S02,1")
        assert self.client.state.power == "on"

    def test_s02_standby(self):
        self.client._process_line("ZQS02!S02,0")
        assert self.client.state.power == "off"

    # -- I00 input info with echo ------------------------------------------

    def test_i00_with_echo(self):
        self.client._process_line("ZQI00!I00,3,A,5")
        s = self.client.state
        assert s.logical_input == 3
        assert s.input_memory == "A"
        assert s.physical_input == 5

    # -- I24 full info with echo -------------------------------------------

    def test_i24_with_echo(self):
        # Realistic v4 response
        fields = ",".join(_make_i24_fields())
        self.client._process_line(f"ZQI24!I24,{fields}")
        s = self.client.state
        assert s.source_vertical_rate == 60
        assert s.source_vertical_resolution == 2160
        assert s.source_content_aspect == "2.40"
        assert s.output_colorspace == "BT.709"
        assert s.source_dynamic_range == "SDR"
        assert s.source_mode == "Progressive"
        assert s.logical_input == 1
        assert s.physical_input == 3
        assert s.detected_raster_aspect == "1.78"
        assert s.detected_content_aspect == "2.40"

    def test_i24_unsolicited(self):
        """Unsolicited mode-change messages have no echo prefix."""
        fields = ",".join(_make_i24_fields(content_aspect="235"))
        self.client._process_line(f"!I24,{fields}")
        assert self.client.state.source_content_aspect == "2.35"

    def test_i21_i22_i23_i25_also_handled(self):
        """All five I2x variants use the same handler."""
        for cmd in ("I21", "I22", "I23", "I24", "I25"):
            client = _make_client()
            fields = ",".join(_make_i24_fields())
            client._process_line(f"ZQ{cmd}!{cmd},{fields}")
            assert client.state.source_vertical_resolution == 2160

    # -- Label responses ---------------------------------------------------

    def test_label_with_pending_id(self):
        self.client._pending_label_id = "A0"
        self.client._label_event = asyncio.Event()
        self.client._process_line("ZQS1A0!S1A,Apple TV")
        assert self.client._last_label_value == "Apple TV"
        assert self.client._label_event.is_set()

    def test_label_id_from_echo(self):
        """When no pending ID, extract from the echoed query."""
        self.client._pending_label_id = None
        self.client._label_event = asyncio.Event()
        self.client._process_line("ZQS1B3!S1B,Blu-ray")
        assert self.client._last_label_value == "Blu-ray"

    def test_label_all_memories(self):
        """Labels from all four input memories are recognized."""
        for mem in "ABCD":
            client = _make_client()
            client._pending_label_id = f"{mem}0"
            client._label_event = asyncio.Event()
            client._process_line(f"ZQS1{mem}0!S1{mem},Test")
            assert client._last_label_value == "Test"

    def test_label_custom_mode(self):
        """Custom mode labels (category 1) are recognized."""
        self.client._pending_label_id = "10"
        self.client._label_event = asyncio.Event()
        self.client._process_line("ZQS110!S11,Custom0")
        assert self.client._last_label_value == "Custom0"

    def test_label_cms(self):
        """CMS labels (category 2) are recognized."""
        self.client._pending_label_id = "20"
        self.client._label_event = asyncio.Event()
        self.client._process_line("ZQS120!S12,CMS0")
        assert self.client._last_label_value == "CMS0"

    def test_label_style(self):
        """Style labels (category 3) are recognized."""
        self.client._pending_label_id = "30"
        self.client._label_event = asyncio.Event()
        self.client._process_line("ZQS130!S13,2.40")
        assert self.client._last_label_value == "2.40"

    # -- Ignored lines -----------------------------------------------------

    def test_pure_echo_ignored(self):
        """Lines with no '!' are echoes and should be ignored."""
        self.client._process_line("ZQS00")
        assert self.state_changes == 0

    def test_empty_line_ignored(self):
        """Empty lines are filtered before _process_line is called,
        but it should still be safe."""
        self.client._process_line("")
        assert self.state_changes == 0

    def test_unknown_response_ignored(self):
        self.client._process_line("!X99,something")
        assert self.state_changes == 0

    def test_noise_from_other_client(self):
        """OSD commands from other TCP clients appear as echo-only lines."""
        self.client._process_line("ZT3Hello World\r")
        assert self.state_changes == 0


# ---------------------------------------------------------------------------
# get_source_list
# ---------------------------------------------------------------------------


class TestGetSourceList:
    def test_with_labels(self):
        client = _make_client()
        client.state.input_memory = "A"
        client.state.input_labels = {
            "A0": "Apple TV",
            "A1": "Blu-ray",
            "A2": "Cable",
        }
        sources = client.get_source_list()
        assert sources[0] == "Apple TV (1)"
        assert sources[1] == "Blu-ray (2)"
        assert sources[2] == "Cable (3)"
        assert sources[3] == "Input (4)"  # fallback
        assert len(sources) == 10

    def test_defaults_to_memory_a(self):
        client = _make_client()
        client.state.input_memory = None
        client.state.input_labels = {"A0": "HDMI 1"}
        assert client.get_source_list()[0] == "HDMI 1 (1)"

    def test_respects_current_memory(self):
        client = _make_client()
        client.state.input_memory = "B"
        client.state.input_labels = {"A0": "Wrong", "B0": "Right"}
        assert client.get_source_list()[0] == "Right (1)"


# ---------------------------------------------------------------------------
# Constants consistency
# ---------------------------------------------------------------------------


class TestConstants:
    def test_all_named_aspects_have_commands(self):
        """Every aspect in ASPECT_RATIO_NAMES should be settable."""
        for code, name in ASPECT_RATIO_NAMES.items():
            assert name in ASPECT_COMMANDS, (
                f"Aspect {name} (code {code}) is in ASPECT_RATIO_NAMES "
                f"but missing from ASPECT_COMMANDS"
            )

    def test_remote_commands_all_single_byte(self):
        """Every remote command should be a single ASCII byte."""
        for name, cmd in REMOTE_COMMANDS.items():
            assert len(cmd) == 1, (
                f"Remote command {name!r} maps to {cmd!r} (not single byte)"
            )
            assert cmd.isascii(), f"Remote command {name!r} maps to non-ASCII {cmd!r}"

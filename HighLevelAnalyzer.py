# High Level Analyzer for TI FSI protocol
# For more information and documentation, please go to https://support.saleae.com/extensions/high-level-analyzer-extensions

# ruff: noqa: T201, PLR2004

from dataclasses import dataclass
from enum import IntEnum, StrEnum, auto

from saleae.analyzers import AnalyzerFrame, HighLevelAnalyzer, NumberSetting
from saleae.data import SaleaeTime


class FsiState(StrEnum):
    IDLE = auto()
    PREAMBLE_SOF = auto()
    FRAMETYPE = auto()
    USERDATA = auto()
    DATA = auto()
    CRC = auto()
    FRAMETAG = auto()
    EOF_POSTAMBLE = auto()


class FsiFrameType(IntEnum):
    PING = 0b0000
    ERROR = 0b1111
    DATA_1_WORD = 0b0100
    DATA_2_WORD = 0b0101
    DATA_4_WORD = 0b0110
    DATA_6_WORD = 0b0111
    DATA_N_WORD = 0b0011


@dataclass
class FsiFrame:
    start_time: SaleaeTime | None = None
    end_time: SaleaeTime | None = None
    preamble: int = 0b1111
    sof: int = 0b1001
    frame_type: FsiFrameType | None = None
    user_data: int | None = None
    data_len: int = 0
    data: tuple[int, ...] | None = None
    crc: int | None = None
    frame_tag: int | None = None
    eof: int = 0b0110
    postamble: int = 0b1111


# High level analyzers must subclass the HighLevelAnalyzer class.
class Hla(HighLevelAnalyzer):
    # Add user configuration
    config_amnt_data_lines = NumberSetting(
        label="Amount of data lines used.",
        min_value=1,
        max_value=2,
    )
    config_data_len = NumberSetting(
        label='Data length in bytes when using "DATA_N_WORD" frame type.',
        min_value=2,
        max_value=32,
    )

    # A list of types this analyzer produces, providing a way to customize the way frames are displayed in Logic 2.
    result_types = {  # noqa: RUF012
        "ti_fsi_frame": {
            "format": "FSI | "
            "Frame Type: {{data.frame_type}} | "
            "User Data: {{data.user_data}} | "
            "Data: {{data.data}} | "
            "CRC: {{data.crc}} | "
            "Frame Tag: {{data.frame_tag}}",
        },
        "ti_fsi_flush": {
            "format": "FSI flush sequence",
        },
    }

    def __init__(self) -> None:
        super().__init__()
        self.state: FsiState | None = FsiState.IDLE
        self.fsi_frame = FsiFrame(
            data_len=self.config_data_len if self.config_data_len is not None else 0,  # type: ignore[arg-type]
        )  # type ignore[call-overload]
        self.fb: list[int] = []  # Init frame buffer to store bits for later
        self.start_times: list[SaleaeTime] = []  # Init start times to have accurate start time after SoF is detected.

        # Process amount of data lines setting
        self.amnt_data_lines = 1
        if self.config_amnt_data_lines is not None and (
            self.config_amnt_data_lines < 1 or self.config_amnt_data_lines > 2  # type: ignore[operator]
        ):
            msg = (
                '[TI FSI] The "Amount of data lines used." setting should be set to "1" or "2", '
                "currently set to {self.config_amnt_data_lines}."
            )
            raise ValueError(msg)
        if self.config_amnt_data_lines is not None and self.config_amnt_data_lines == 2:
            self.amnt_data_lines = 2

    def decode(self, frame: AnalyzerFrame) -> AnalyzerFrame | None:  # noqa: C901, PLR0912, PLR0915
        """Decode an FSI frame as described in section 12.4.5.4.4 of TI AM243x Technical Reference Manual (SPRUIM2I)."""
        # First check correct frame type and get the bits from the frame
        if frame.type != "data" or not isinstance(frame.data["data"], int):
            msg = "[TI FSI] Analyzer only works with the 'Simple Parallel' input analyzer!"
            raise NotImplementedError(msg)

        bits = frame.data["data"]

        # Add bits to the frame buffer, how multi-lane data is handled depends on the state
        if self.amnt_data_lines == 2 and self.state in (FsiState.USERDATA, FsiState.DATA, FsiState.CRC):
            # userdata, data and crc can support two data lines.
            # The data bits are alternated between the data lines, with the msb first on the first data line.
            if bits == 0:
                self.fb.append(0)
                self.fb.append(0)
            elif bits == 1:
                self.fb.append(1)
                self.fb.append(0)
            if bits == 2:
                self.fb.append(0)
                self.fb.append(1)
            elif bits == 3:
                self.fb.append(1)
                self.fb.append(1)
            else:
                msg = f"Data value is out-of-range, should be between 0-3, got {bits}. "
                "Are the correct amount of data lines used in the analyzer settings?"
                raise ValueError(msg)
        else:
            self.fb.append(bits & 1)

        # Process statemachine
        while True:
            match self.state:
                case FsiState.IDLE:
                    self.fsi_frame = FsiFrame(data_len=self.config_data_len if self.config_data_len is not None else 0)  # type: ignore[arg-type]
                    self.start_times.clear()
                    self.state = FsiState.PREAMBLE_SOF
                    continue
                case FsiState.PREAMBLE_SOF:
                    self.start_times.append(frame.start_time)
                    if len(self.fb) >= 8 and self.fb[-8:] == [1, 1, 1, 1, 1, 0, 0, 1]:
                        self.fsi_frame.start_time = self.start_times[-8]
                        self.fsi_frame.preamble = 0b1111
                        self.fsi_frame.sof = 0b1001
                        self.fb.clear()
                        self.start_times.clear()
                        self.state = FsiState.FRAMETYPE
                    elif len(self.fb) >= 10 and self.fb[-10:] == [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]:
                        # Flush sequence detected
                        self.fsi_frame.start_time = self.start_times[-10]
                        self.fsi_frame.end_time = frame.start_time
                        self.fb.clear()
                        self.state = FsiState.IDLE
                        # Return analyzerframe for flush sequence
                        return AnalyzerFrame("ti_fsi_flush", self.fsi_frame.start_time, self.fsi_frame.end_time)
                    break
                case FsiState.FRAMETYPE:
                    if len(self.fb) < 4:
                        break
                    try:
                        fsi_frame_type = FsiFrameType(self._bitlist_to_byte(self.fb))
                    except ValueError:  # Error
                        print(f"[TI FSI] Invalid frame type: {self._bitlist_to_byte(self.fb)}")
                        self.state = None
                        continue
                    self.fsi_frame.frame_type = fsi_frame_type
                    self.fb.clear()
                    if fsi_frame_type in (FsiFrameType.PING, FsiFrameType.ERROR):
                        self.state = FsiState.FRAMETAG
                    else:
                        if fsi_frame_type == FsiFrameType.DATA_1_WORD:
                            self.fsi_frame.data_len = 2
                        elif fsi_frame_type == FsiFrameType.DATA_2_WORD:
                            self.fsi_frame.data_len = 4
                        elif fsi_frame_type == FsiFrameType.DATA_4_WORD:
                            self.fsi_frame.data_len = 8
                        elif fsi_frame_type == FsiFrameType.DATA_6_WORD:
                            self.fsi_frame.data_len = 12
                        self.state = FsiState.USERDATA
                    break
                case FsiState.USERDATA:
                    if len(self.fb) < 8:
                        break
                    self.fsi_frame.user_data = self._bitlist_to_byte(self.fb)
                    self.fb.clear()
                    self.state = FsiState.DATA
                    break
                case FsiState.DATA:
                    if len(self.fb) < (self.fsi_frame.data_len * 8):
                        break
                    self.fsi_frame.data = tuple(self._bitlist_to_bytelist(self.fb))
                    self.fb.clear()
                    self.state = FsiState.CRC
                    break
                case FsiState.CRC:
                    if len(self.fb) < 8:
                        break
                    self.fsi_frame.crc = self._bitlist_to_byte(self.fb)
                    # Check CRC
                    crc_bytes = b""
                    crc_bytes += self.fsi_frame.user_data.to_bytes(1, "little")  # type: ignore[union-attr]
                    for i in range(0, len(self.fsi_frame.data), 2):  # type: ignore[arg-type]
                        crc_bytes += self.fsi_frame.data[i + 1].to_bytes(1, "little")  # type: ignore[index]
                        crc_bytes += self.fsi_frame.data[i].to_bytes(1, "little")  # type: ignore[index]
                    calc_crc = self._crc8(crc_bytes)
                    if calc_crc != self.fsi_frame.crc:
                        print(f"[TI FSI] CRC is incorrect, got: {hex(self.fsi_frame.crc)}, calculated: {hex(calc_crc)}")
                    self.fb.clear()
                    self.state = FsiState.FRAMETAG
                    break
                case FsiState.FRAMETAG:
                    if len(self.fb) < 4:
                        break
                    self.fsi_frame.frame_tag = self._bitlist_to_byte(self.fb)
                    self.fb.clear()
                    self.state = FsiState.EOF_POSTAMBLE
                    break
                case FsiState.EOF_POSTAMBLE:
                    if len(self.fb) < 8:
                        break
                    if self.fb == [0, 1, 1, 0, 1, 1, 1, 1]:
                        self.fsi_frame.end_time = frame.start_time
                        self.fsi_frame.eof = 0b0110
                        self.fsi_frame.postamble = 0b1111
                        self.fb.clear()
                        self.state = FsiState.IDLE
                        # Return analyzerframe
                        return AnalyzerFrame(
                            "ti_fsi_frame",
                            self.fsi_frame.start_time,
                            self.fsi_frame.end_time,
                            {
                                "frame_type": self.fsi_frame.frame_type.name if self.fsi_frame.frame_type else "None",
                                "user_data": hex(self.fsi_frame.user_data) if self.fsi_frame.user_data else "None",
                                "data": " ".join(hex(b) for b in self.fsi_frame.data)
                                if self.fsi_frame.data
                                else "None",
                                "crc": hex(self.fsi_frame.crc) if self.fsi_frame.crc else "None",
                                "frame_tag": hex(self.fsi_frame.frame_tag) if self.fsi_frame.frame_tag else "None",
                            },
                        )
                    # Error
                    self.state = None
                    continue
                case _:
                    print("[TI FSI] State machine in invalid state, frame corrupt!")
                    print(f"[TI FSI] Corrupt frame: {self.fsi_frame}")
                    self.state = FsiState.IDLE
                    continue

        return None

    def _bitlist_to_byte(self, bitlist: list[int]) -> int:
        # Only works with max 8 bits
        if len(bitlist) > 8:
            msg = f"[TI FSI] _bitlist_to_byte only allows up to 8 bits, provided {len(bitlist)} bits!"
            raise ValueError(msg)
        byte_val = 0
        for bit in bitlist:
            byte_val = (byte_val << 1) | bit
        return byte_val

    def _bitlist_to_bytelist(self, bitlist: list[int]) -> list[int]:
        bytelist = []
        if len(bitlist) % 8:
            # append 0 to get multiple of 8
            bitlist.extend([0] * (8 - (len(bitlist) % 8)))
        for i in range(0, len(bitlist), 8):
            byte_val = 0
            for bit in bitlist[i : i + 8]:
                byte_val = (byte_val << 1) | bit
            bytelist.append(byte_val)
        return bytelist

    def _crc8(self, data: bytes, poly: int = 0x07, init: int = 0x00) -> int:
        """Compute an 8-bit CRC (CRC-8) for the given byte sequence."""
        crc = init
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:  # if the left-most bit is set  # noqa: SIM108
                    crc = ((crc << 1) ^ poly) & 0xFF
                else:
                    crc = (crc << 1) & 0xFF
        return crc

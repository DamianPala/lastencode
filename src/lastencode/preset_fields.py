"""The value vocabulary shared by TOML validation and introspection."""

from dataclasses import dataclass

from lastencode.errors import InvalidInput

type Value = str | int | bool

TARGETS = ("portable", "desktop")
MAX_FILE_BYTES = 1_048_576
MAX_CATEGORIES = 256
SPEED_PRESETS = (
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
    "placebo",
    *(str(number) for number in range(14)),
)


@dataclass(frozen=True)
class Field:
    kind: type[str] | type[int] | type[bool]
    description: str
    choices: tuple[Value, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    allow_native: bool = False

    def validate(self, value: object, path: str) -> Value:
        if path.endswith(".copy_video_below_bps") and value == "never":
            return "never"
        if self.allow_native and value == "native":
            return "native"
        if type(value) is not self.kind:
            raise InvalidInput(f"{path}: expected {self.kind.__name__}, got {value!r}")
        assert isinstance(value, str | int | bool)
        if self.choices and value not in self.choices:
            raise InvalidInput(f"{path}: invalid value {value!r}; valid values: {self.choices}")
        if isinstance(value, int) and self.minimum is not None and value < self.minimum:
            raise InvalidInput(f"{path}: expected at least {self.minimum}, got {value}")
        if isinstance(value, int) and self.maximum is not None and value > self.maximum:
            raise InvalidInput(f"{path}: expected at most {self.maximum}, got {value}")
        return value


FIELDS = {
    "encoder": Field(str, "FFmpeg software video encoder.", ("libx265", "libsvtav1")),
    "quality_crf": Field(int, "Constant rate factor (CRF).", minimum=0, maximum=63),
    "speed_preset": Field(
        str, "x265 speed name or SVT-AV1 preset number as a string.", SPEED_PRESETS
    ),
    "extra_encoder_params": Field(str, "Colon-separated encoder parameters."),
    "deblocking": Field(str, "Encoder deblocking parameters; default keeps encoder defaults."),
    "bit_depth": Field(int, "Video bit depth.", (8, 10)),
    "scale_short_side": Field(int, "Short side in pixels, shrink only; 0 means native.", minimum=0),
    "audio_codec": Field(str, "Audio codec.", ("opus", "aac")),
    "audio_bitrate_bps": Field(int, "Audio bitrate in bits per second.", minimum=1),
    "audio_channel_rule": Field(
        str,
        "Preserve channels, or mono for dual-mono sources and stereo otherwise.",
        ("preserve", "dual-mono-to-mono-otherwise-stereo"),
    ),
    "audio_dual_mono_bitrate_bps": Field(
        int, "Bitrate for dual-mono input under the conditional channel rule.", minimum=1
    ),
    "keyframe_interval_seconds": Field(int, "Maximum keyframe spacing in seconds.", minimum=1),
    "copy_video_below_bps": Field(
        int, "Copy video below this bitrate in bits per second, or never.", minimum=0
    ),
    "max_frame_rate": Field(
        int,
        "Maximum encoded frame rate in frames per second, or native to preserve the source.",
        minimum=1,
        allow_native=True,
    ),
    "drop_repeated_frames": Field(bool, "Drop repeated frames under R10a."),
}

from dataclasses import dataclass
from typing import Optional, TypedDict

class _TTSParamsBase(TypedDict):
    text: str

class AIVISParams(_TTSParamsBase,TypedDict):
    model_uuid:str
    speaker_uuid:Optional[str]
    style_id:Optional[str]
    style_name:Optional[str]
    language: str
    use_ssml: bool
    speaking_rate: float
    emotional_intensity: float
    tempo_dynamics: float
    pitch: float
    olume: float
    leading_silence_seconds: float
    trailing_silence_seconds: float
    line_break_silence_seconds: float
    output_format: str
    output_sampling_rate: int
    output_audio_channels: str

class BV2Params(_TTSParamsBase, TypedDict):
    speaker_id: int
    audio_format: str
    lang: str
    length: float
    noise: float
    noisew: float
    segment_size: int
    sdp_radio: float

class VitsParams(_TTSParamsBase, TypedDict):
    ref_audio_path: str
    prompt_language: str
    text_language: str
    speed_factor: float
    text_split_method: str
    top_k: int
    top_p: float
    temperature: float

class GPTSoVITSParams(_TTSParamsBase, TypedDict):
    prompt_language: str
    text_language: str
    speed_factor: float
    text_split_method: str
    top_k: int
    top_p: float
    temperature: float

@dataclass
class TTSResult:
    audio: bytes
    audio_path: Optional[str] = None
    audio_bytes: Optional[bytes] = None
    audio_url: Optional[str] = None
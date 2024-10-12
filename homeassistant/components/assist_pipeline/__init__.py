"""The Assist pipeline integration."""

from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Any, cast

import voluptuous as vol

from homeassistant.components import stt
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_DEBUG_RECORDING_DIR,
    DATA_CONFIG,
    DATA_LAST_WAKE_UP,
    DOMAIN,
    EVENT_RECORDING,
    OPTION_PREFERRED,
    SAMPLE_CHANNELS,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    SAMPLES_PER_CHUNK,
)
from .error import PipelineNotFound
from .pipeline import (
    AudioSettings,
    Pipeline,
    PipelineEvent,
    PipelineEventCallback,
    PipelineEventType,
    PipelineInput,
    PipelineRun,
    PipelineStage,
    WakeWordSettings,
    async_create_default_pipeline,
    async_get_pipeline,
    async_get_pipelines,
    async_migrate_engine,
    async_run_migrations,
    async_setup_pipeline_store,
    async_update_pipeline,
)
from .websocket_api import async_register_websocket_api

__all__ = (
    "DOMAIN",
    "async_create_default_pipeline",
    "async_get_pipelines",
    "async_migrate_engine",
    "async_setup",
    "AudioStreamPipelineBuilder",
    "async_update_pipeline",
    "AudioSettings",
    "Pipeline",
    "PipelineEvent",
    "PipelineEventType",
    "PipelineNotFound",
    "WakeWordSettings",
    "EVENT_RECORDING",
    "OPTION_PREFERRED",
    "SAMPLES_PER_CHUNK",
    "SAMPLE_RATE",
    "SAMPLE_WIDTH",
    "SAMPLE_CHANNELS",
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_DEBUG_RECORDING_DIR): str,
            },
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Assist pipeline integration."""
    hass.data[DATA_CONFIG] = config.get(DOMAIN, {})

    # wake_word_id -> timestamp of last detection (monotonic_ns)
    hass.data[DATA_LAST_WAKE_UP] = {}

    await async_setup_pipeline_store(hass)
    await async_run_migrations(hass)
    async_register_websocket_api(hass)

    return True


class AudioStreamPipelineBuilder:
    """Builds an audio stream pipeline for Home Assistant."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the AssistPipeline with HomeAssistant instance. Sets all parameters to None by default."""
        self.hass = hass
        self.context: Context | None = None
        self.event_callback: PipelineEventCallback | None = None
        self.stt_metadata: stt.SpeechMetadata | None = None
        self.stt_stream: AsyncIterable[bytes] | None = None
        self.wake_word_phrase: str | None = None
        self.pipeline_id: str | None = None
        self.conversation_id: str | None = None
        self.tts_audio_output: str | dict[str, Any] | None = None
        self.wake_word_settings: WakeWordSettings | None = None
        self.audio_settings: AudioSettings | None = None
        self.device_id: str | None = None
        self.start_stage: PipelineStage = PipelineStage.STT
        self.end_stage: PipelineStage = PipelineStage.TTS

    async def build(self) -> None:
        """Create an audio pipeline from an audio stream.

        Raises PipelineNotFound if no pipeline is found.
        """
        if not all(
            [self.context, self.event_callback, self.stt_metadata, self.stt_stream]
        ):
            raise ValueError("Missing required parameters")
        run = PipelineRun(
            self.hass,
            context=cast(Context, self.context),
            pipeline=async_get_pipeline(self.hass, pipeline_id=self.pipeline_id),
            start_stage=self.start_stage,
            end_stage=self.end_stage,
            event_callback=cast(PipelineEventCallback, self.event_callback),
            tts_audio_output=self.tts_audio_output,
            wake_word_settings=self.wake_word_settings,
            audio_settings=self.audio_settings or AudioSettings(),
        )
        pipeline_input = PipelineInput(
            conversation_id=self.conversation_id,
            device_id=self.device_id,
            stt_metadata=cast(stt.SpeechMetadata, self.stt_metadata),
            stt_stream=cast(AsyncIterable[bytes], self.stt_stream),
            wake_word_phrase=self.wake_word_phrase,
            run=run,
        )
        await pipeline_input.validate()
        await pipeline_input.execute()

"""Shared lazy CTranslate2/SentencePiece adapter machinery."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar

from edc_translation.engines.base import EngineTranslation, TranslationEngine
from edc_translation.provenance import load_model_provenance_from_dir

DEVICE_ENV = "EDC_TRANSLATION_CT2_DEVICE"


class CT2SentencePieceEngine(TranslationEngine):
    """Base class for local CT2 engines with SentencePiece tokenizers."""

    model_dir_env: ClassVar[str]
    tokenizer_files: ClassVar[tuple[str, str]] = ("source.spm", "target.spm")
    confidence: ClassVar[float] = 0.85

    def __init__(
        self,
        model_dir: str | os.PathLike[str] | None = None,
        *,
        device: str | None = None,
    ) -> None:
        configured_dir = (
            str(model_dir)
            if model_dir is not None
            else os.getenv(self.model_dir_env, "")
        )
        self._model_dir = Path(configured_dir) if configured_dir else None
        self._device = device or os.getenv(DEVICE_ENV, "cpu")
        self._translator: Any | None = None
        self._source_tokenizer: Any | None = None
        self._target_tokenizer: Any | None = None
        self._runtime_version = "not_loaded"
        self._provenance: dict[str, Any] | None = None

    def translate_text(
        self,
        text: str,
        *,
        source_language: str,
        target_language: str,
    ) -> EngineTranslation:
        del source_language, target_language

        self._ensure_loaded()
        assert self._translator is not None
        assert self._source_tokenizer is not None
        assert self._target_tokenizer is not None

        tokenized = self._source_tokenizer.encode(text, out_type=str)
        result = self._translator.translate_batch(
            [tokenized],
            beam_size=4,
            max_decoding_length=256,
            replace_unknowns=True,
        )[0]
        translated_text = self._target_tokenizer.decode(result.hypotheses[0])
        return EngineTranslation(
            translated_text=translated_text,
            confidence=self.confidence,
            quality_score=None,
        )

    def model_provenance(self) -> dict[str, Any]:
        if self._provenance is not None:
            return self._provenance

        payload = self._load_model_provenance_file()
        if payload is None:
            payload = {
                "weights_sha256": self._model_sha256(),
                "license": self.capability.license,
                "runtime": "ctranslate2",
                "runtime_version": self.runtime_info()["version"],
                "model_dir_env": self.model_dir_env,
                "model_dir_configured": self._model_dir is not None,
            }
        self._provenance = payload
        return self._provenance

    def runtime_info(self) -> dict[str, str]:
        return {"runtime": "ctranslate2", "version": self._runtime_version}

    def _ensure_loaded(self) -> None:
        if self._translator is not None:
            return
        if self._model_dir is None:
            raise RuntimeError(
                f"{self.capability.id} requires a model directory. "
                f"Set {self.model_dir_env} or pass model_dir explicitly."
            )

        source_file, target_file = self.tokenizer_files
        source_spm = self._model_dir / source_file
        target_spm = self._model_dir / target_file
        if not source_spm.is_file() or not target_spm.is_file():
            raise RuntimeError(
                f"{self.capability.id} model_dir must contain "
                f"{source_file} and {target_file}"
            )

        try:
            import ctranslate2
            import sentencepiece as spm
        except ImportError as exc:
            raise RuntimeError(
                f"{self.capability.id} requires optional dependencies: "
                "ctranslate2 and sentencepiece"
            ) from exc

        self._runtime_version = str(getattr(ctranslate2, "__version__", "unknown"))
        self._translator = ctranslate2.Translator(
            str(self._model_dir),
            device=self._device,
        )
        self._source_tokenizer = spm.SentencePieceProcessor(
            model_file=str(source_spm)
        )
        self._target_tokenizer = spm.SentencePieceProcessor(
            model_file=str(target_spm)
        )
        self._provenance = None

    def _load_model_provenance_file(self) -> dict[str, Any] | None:
        if self._model_dir is None:
            return None

        try:
            return load_model_provenance_from_dir(self._model_dir)
        except FileNotFoundError:
            return None

    def _model_sha256(self) -> str:
        if self._model_dir is None:
            return "not_loaded"

        sha_path = self._model_dir / "MODEL_SHA256"
        if not sha_path.is_file():
            return "not_loaded"
        return sha_path.read_text(encoding="utf-8").strip() or "not_loaded"

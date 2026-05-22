# Contracts Reference

EDC Translation is built around two public JSON contracts:

- `DocumentBundle v1`: input document text and source-span envelope.
- `TranslationBundle v1`: translated-span output envelope with provider and evidence metadata.

The schemas live at:

- [schemas/document-bundle-v1.schema.json](../schemas/document-bundle-v1.schema.json)
- [schemas/translation-bundle-v1.schema.json](../schemas/translation-bundle-v1.schema.json)

Packaged schema copies live under [edc_translation/schemas](../edc_translation/schemas).

## DocumentBundle v1

Required top-level fields:

| Field | Purpose |
|---|---|
| `schema_version` | Must be `document-bundle-v1`. |
| `document_id` | Stable document identifier. |
| `source_file_name` | Original file name or source label. |
| `source_file_sha256` | SHA-256 of the source file. |
| `source_ocr_sha256` | SHA-256 of the upstream text/OCR artifact. |
| `pages` | Page envelopes with page numbers and span IDs. |
| `spans` | Source spans with IDs, text, page numbers, and bounding boxes. |
| `language_metadata` | Primary/detected language metadata. |
| `ocr_engine_metadata` | Upstream text/OCR engine metadata. |
| `custody_chain_head` | Current custody hash/reference. |
| `artifact_manifest` | Referenced artifacts. |

## TranslationBundle v1

Required top-level fields:

| Field | Purpose |
|---|---|
| `schema_version` | Must be `translation-bundle-v1`. |
| `document_id` | Source document identifier. |
| `source_ocr_sha256` | Links to upstream text/OCR artifact. |
| `source_bundle_sha256` | Links to exact source bundle. |
| `target_language` | Target language tag. |
| `translated_spans` | Translated spans preserving source identity. |
| `engine_provider` | Provider ID, family, local/cloud flag, license, retention class. |
| `model_provenance` | Model/runtime provenance metadata. |
| `quality_scores` | Aggregate quality metadata. |
| `certified` | Certification flag. |
| `custody_chain_head` | Updated custody hash/reference. |
| `artifact_manifest` | Output artifacts. |

## Span Linkage

Every translated span preserves:

- `span_id`
- `page_number`
- `source_text`
- `translated_text`
- `source_bbox`
- `source_bboxes`
- `source_language`
- `target_language`
- `confidence`
- `quality_score`
- `engine_id`
- `glossary_hits`

This lets downstream systems trace translated text back to the originating document span.

## Compatibility Rules

- Treat schema versions as explicit contracts.
- Do not remove required fields from existing schema versions.
- Add optional fields only when old consumers can safely ignore them.
- Preserve `additionalProperties: false` where the schema intentionally prevents unknown fields.
- Keep package-data schema copies synchronized with root schema copies.
- Update fixtures and docs whenever schema behavior changes.

## Validation Commands

```bash
edc-translation translate tests/fixtures/edc_contracts/document-bundle-v1.valid.json --target fr --provider deterministic_ci
python -m pytest -q tests/test_contracts.py tests/test_service.py
```

## Integration Guidance

Producers should validate before submitting. Consumers should validate returned bundles before writing them to long-lived storage. When validation fails, treat the payload as incompatible rather than trying to repair it silently.

# Batch Text Translation

Batch text translation processes folders or single text files and writes translated output, optional sidecar bundles, logs, and manifests.

## Use It When

- You already have plain text files.
- You need repeatable local translation over many files.
- You want sidecar `TranslationBundle v1` metadata for each file.

## Avoid It When

- Users should not have direct filesystem access.
- You need OCR extraction from images.
- You cannot define allowed source and output roots.

## API Route

`POST /api/v1/translation/files/batch`

Important fields:

| Field | Purpose |
|---|---|
| `source_path` | Input file or directory. |
| `output_dir` | Output directory. |
| `target_language` | Target language. |
| `provider_id` | Provider used for files. |
| `recursive` | Whether to walk directories. |
| `file_extensions` | File extension allow-list. |
| `write_translation_bundles` | Sidecar JSON output. |
| `write_manifest` | Batch manifest output. |

## Safety Rules

- Restrict filesystem roots in deployment.
- Use least-privilege process users.
- Keep outputs outside source control by default.
- Use deterministic provider for public smoke tests.

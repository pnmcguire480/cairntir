# Repository formatter settings

The maintained normal-pytest wrapper now uses the candidate repository's Ruff
configuration (line length 100), rather than Ruff's default configuration used
outside a checkout. Only formatting bytes change; tests and assertions retain
the version-4 contract. Version 4 is preserved under history/v4. This correction
precedes candidate verification and the active count remains 45 pytest cases.

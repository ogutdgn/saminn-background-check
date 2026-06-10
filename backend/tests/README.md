# backend/tests/

Per-adapter tests that run against **captured fixtures**, so the suite is fast and
doesn't hammer live government sites.

## Layout

```
tests/
├── fixtures/
│   └── <county>/        # raw HTML/JSON captured during Stage 1 of the pipeline
└── test_<county>.py     # feeds fixtures through the adapter, asserts the output
```

## What each adapter's test must cover

(See the Stage 3 gate in [`../../docs/ADDING_A_SOURCE.md`](../../docs/ADDING_A_SOURCE.md).)

- A **multi-result** query — including pagination if the source pages.
- A **no-results** query.
- Correct `matched_on` tagging (real name vs alias vs attorney).

## Why fixtures, not live calls

Live sites go down, change, and rate-limit. Fixtures captured during the data-pull
spike let us:
- develop and test offline,
- prove regressions when a site changes its HTML,
- run CI without external dependencies.

`pytest` is set up in Phase 1. Fixtures hold **real public records (incl. mugshots)**
— they are git-ignored by default; check the policy with the lead before committing
any fixture that contains PII.

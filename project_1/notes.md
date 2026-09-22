# Project 1 notes 
## set up 
after setup,  21 passed, 0 failed
URLs evaluated     : 24
  Mean absolute error: 0.142   (lower is better; 0.000 is perfect)
  Band accuracy      : 66.7%   (HIGH/MEDIUM/LOW chip correct)
  Worst single error : 0.410
  LLM layer          : off (rules only)

Moved project folder to fix nested-repo issue
Fixed pyarrow build failure by pinning `uv sync --python 3.12`
## Sept 19 — Weakness #1: reading the actual page

### What I built
- Added `_fetch_page(url)` — fetches a URL with `requests`, parses it with BeautifulSoup,
  returns None on any failure (timeout, dead link, non-200 status) so one bad URL can't crash scoring
- Added `content_signals(url)` — checks the fetched page for:
  - a named author (meta tag or "By First Last" pattern) → +0.05
  - a publish date (meta tag or <time> element) → +0.05
  - references/citations/bibliography mentioned → +0.05
- Wired into `score_url()`: `signals = rule_based_signals(url) + content_signals(url)`

### Debugging notes (for my own reference)
- First test run showed zero change — turned out `credibility.py` had unsaved
  changes in VS Code (white dot on the tab = unsaved). Ctrl+S fixed it.
- Even after saving, evaluate.py still showed no change — stale __pycache__
  bytecode was the cause. Cleared with:
  `Get-ChildItem -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force`
- Lesson: always save the file AND clear __pycache__ before re-testing if
  results look unexpectedly unchanged.

### Results (rules only, no LLM)
| Metric              | Baseline | After #1 |
|---------------------|----------|----------|
| MAE                 | 0.142    | 0.145    |
| Band accuracy       | 66.7%    | 66.7%    |
| Worst single error  | 0.410    | 0.410    |

### Key finding: fetch blocking
Tested which sites actually allow fetching:
- OK: nature.com, en.wikipedia.org, arxiv.org
- FAIL (403 Forbidden — blocked): jamanetwork.com, who.int, reuters.com

JAMA, WHO, IMF, Reuters all stayed exactly the same score because the page
fetch is blocked outright (403), even with a browser-like User-Agent header.
This is a real limitation of the URL-fetching approach, not a bug in my code.

### Key finding: references signal helped arXiv the wrong way
arXiv moved from 0.77 to 0.87 (expected 0.65) — WORSE, not better. Reason:
arXiv preprints have a References section just like peer-reviewed papers do,
so `has_references` fired and pushed the score up. But a preprint should
score LOWER regardless of having references, since it hasn't been peer
reviewed. This directly motivates fixing Weakness #3 next (preprint
detection), since it should correct this specific regression.

### Next up
- Weakness #3: detect preprints (arxiv.org, biorxiv.org) and penalize
  appropriately instead of treating them like peer-reviewed sources
- Weakness #9: test different RULE_WEIGHT / LLM_WEIGHT splits (needs API key)

## Weakness #3: preprint detection

### What I built
- Added `PREPRINT_DOMAINS` set (arxiv.org, biorxiv.org, medrxiv.org, ssrn.com)
  and `PREPRINT_PENALTY = -0.15`
- Added a Signal 6 check in `rule_based_signals()`: if the domain is a known
  preprint server, apply the penalty regardless of other positive signals
  (having references doesn't mean peer-reviewed)

### Bug encountered
First attempt placed the new signal check AFTER `return signals` in the
function — dead code that silently never ran. No error, no crash, just
had zero effect. Moved the check above the `return` statement to fix.
Lesson: a `return` statement ends a function immediately; anything after
it in the same function never executes.

### Results (rules only, cumulative with #1)
| Metric              | Original baseline | After #1 alone | After #1 + #3 |
|---------------------|--------------------|-----------------|-----------------|
| MAE                 | 0.142              | 0.145           | 0.133           |
| Band accuracy       | 66.7%              | 66.7%           | 70.8%           |
| Worst single error  | 0.410              | 0.410           | 0.410           |

arXiv error dropped from 0.22 off to 0.07 off; bioRxiv from 0.32 off to
0.17 off. Confirms the preprint penalty directly fixed the regression that
#1 introduced (references signal wrongly rewarding unreviewed preprints).

Worst error is still JAMA (unchanged) — still blocked by 403, unrelated
to this fix.

### Next up
- Weakness #9: test RULE_WEIGHT / LLM_WEIGHT splits (needs API key — get
  one at console.anthropic.com, separate from Claude Pro subscription)





## Weakness #9: testing the rule/LLM blend weight

### Bug found: API key never loaded
`llm_opinion()` checks `os.getenv("ANTHROPIC_API_KEY")`, but nothing in
`credibility.py` or `evaluate.py` ever called `load_dotenv()`. This meant
the key silently appeared "missing" even with a valid `.env` file, so
`evaluate.py --llm` was quietly running rules-only the whole time —
no error, no warning, just wrong numbers.

Note: this bug is separate from Weaknesses #1 and #3 (content_signals and
preprint detection) — neither of those touch the API key, so their
results (MAE 0.133, 70.8% band accuracy) are unaffected and still valid.

Fix: added to credibility.py imports:
```python
from dotenv import load_dotenv
load_dotenv()
```
This loads .env the moment credibility.py is imported by anything
(evaluate.py, tests, the app), rather than relying on each script to
remember to call it separately.

### Testing RULE_WEIGHT / LLM_WEIGHT splits
Original constant (0.6 rules / 0.4 LLM) was never tested — confirmed
in the assignment's own comments. Tested three splits with evaluate.py --llm:

| Split (rule/LLM) | MAE   | Band accuracy | Worst error |
|-------------------|-------|----------------|-------------|
| 0.6 / 0.4 (original) | 0.088 | 83.3%          | 0.230       |
| 0.3 / 0.7          | 0.061 | 91.7%          | 0.130       |
| 0.1 / 0.9          | 0.058 | 87.5%          | 0.180       |

0.1/0.9 had the lowest MAE by a hair, but WORSE band accuracy and worst
error than 0.3/0.7 — over-weighting the LLM diluted useful rule-layer
signal (e.g. scikit-learn's docs page got worse, not better). Chose
0.3/0.7 as the best overall balance across all three metrics, not just
the single lowest MAE.

### Final chosen weights
RULE_WEIGHT = 0.3
LLM_WEIGHT = 0.7

### Cumulative results summary
| Stage                        | MAE   | Band accuracy | Worst error |
|-------------------------------|-------|----------------|-------------|
| Original baseline             | 0.142 | 66.7%          | 0.410       |
| + #1 (read the page)          | 0.145 | 66.7%          | 0.410       |
| + #3 (preprint detection)     | 0.133 | 70.8%          | 0.410       |
| + LLM layer (0.6/0.4 default) | 0.088 | 83.3%          | 0.230       |
| + #9 (tuned to 0.3/0.7)       | 0.061 | 91.7%          | 0.130       |

### Note on run-to-run variance
Reran evaluate.py --llm after locking in 0.3/0.7 and got MAE 0.061 (matches),
but band accuracy 87.5% and worst error 0.130 on a DIFFERENT URL (scikit-learn
docs instead of arXiv) — a few points different from the earlier 0.3/0.7 test
run (91.7%). This is expected: the LLM layer is not deterministic like the
rules layer, so scores can shift slightly between runs even with unchanged
code. Something to note as a limitation in the report — the reported numbers
carry some natural variance from the LLM itself, not just from the algorithm.

## Sept 21 — Part 1 requirement: own test case

Added one test to test_credibility.py (first edit to this file — everything
before this was in credibility.py):

```python
print("\nMy test: preprint domains are flagged")
result = score_url("https://arxiv.org/abs/1706.03762", use_llm=False)
check("preprint" in result["explanation"].lower(), "arXiv is flagged as a preprint")
```

Tests that my own Weakness #3 fix (preprint detection) actually shows up in
the explanation text, not just the score. Matches the file's existing style
(plain check() calls, no pytest).

Result: 22 passed, 0 failed (up from 21 — the 21 original contract tests
plus this one new case).

This completes Part 1's four grading items:
- score_url() returns correct contract — already passing
- malformed input handled without raising — already passing
- substantive improvement clearly identified — #1, #3, #9
- own added test case — this entry
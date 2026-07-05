# ZBS Template Validation Tool — Challenge 2

## Folder structure

```
validator/
├── rule_map.md              # Full rule map (Step 1) — 5 rule groups + reasoning for which rules to automate
├── validator.py              # Validation tool (Step 2)
├── sample_inputs/            # 5 sample JSON inputs
│   ├── template_01_pass.json                  # Valid — expected PASS
│   ├── template_02_param_link_issues.json     # Bad parameter format + link/phone in content + shortlink
│   ├── template_03_voucher_birthday.json      # Birthday template missing image + missing Voucher Template
│   ├── template_04_banned_industry.json       # Industry absolutely banned from Tag 3 (funeral services)
│   └── template_05_tpcn_missing_legal.json    # Dietary supplement missing mandatory legal disclaimer
└── sample_outputs/           # Corresponding output JSON (already run)
```

## Try it out

```bash
python validator.py sample_inputs/template_01_pass.json          # prints to stdout
python validator.py sample_inputs/*.json --out sample_outputs/   # writes to file
```

## Input schema (summary — see examples in sample_inputs/)

| Field | Type | Meaning |
|---|---|---|
| `template_name` | string | Identifier name for the template |
| `tag` | 1 / 2 / 3 | Transaction / Customer Care / Promotional |
| `purpose` | string | Purpose of the message |
| `industry` | string | Industry/product group |
| `content` | string | Template content, parameters written as `{param_name}` or `<param_name>` |
| `parameters` | array[{name, example}] | List of declared parameters |
| `cta` | array[{type, label, value}] | CTA button: `url`, `phone_number`, `quick_reply`... |
| `has_image` | bool | Whether the template includes an image/banner |
| `use_voucher_template` | bool | Whether the dedicated "Voucher Template" type is being used |

## 9 automated rules (see `rule_map.md` for the reasoning behind each choice)

| Rule ID | What it checks |
|---|---|
| R1_PARAM_FORMAT / R1_PARAM_UNUSED | Parameter format is correct (no accents, no spaces, no personal pronouns); parameters declared but unused |
| R2_LINK_IN_CONTENT / R2_PHONE_IN_CONTENT | Links/phone numbers inserted directly into content instead of the CTA |
| R3_SHORTLINK_CTA / R3_SOCIAL_GROUP_CTA | CTA uses a shortlink, or links to an unofficial chat group/social media |
| R4_MIN_PARAMS | Minimum number of identifying parameters required per Tag |
| R5_VOUCHER_TEMPLATE_REQUIRED | Content mentions a voucher/discount but doesn't use the Voucher Template |
| R6_BIRTHDAY_*/R6_HOLIDAY_* | Birthday/Holiday templates missing an image or missing mandatory offer details |
| R7_INDUSTRY_FULLY_BANNED / R7_INDUSTRY_TAG3_BANNED | Industry is fully banned, or banned from being tagged Tag 3 |
| R8_TPCN_LEGAL_TEXT / R8_ALCOHOL_LEGAL_TEXT | Missing mandatory legal disclaimer text for the industry |
| R9_EMOJI_IN_CONTENT / R9_SUPERSTITION_LANGUAGE | Inappropriate icons/emoji; superstition-related language |

## Rules NOT automated (and why)

See the "Automatable?" column in `rule_map.md`. In short: any rule that needs image OCR, license/legal verification, or cross-referencing a customer's actual transaction data (outside the scope of a single JSON template) is left to the human reviewer — because getting this category wrong (a false "pass") is riskier than not automating it at all.

## Known limitations (stated plainly, no sugarcoating)

- Holiday detection relies on a "holiday" keyword after normalization — a v2 should classify purpose using a lightweight NLP model or a longer list of phrases instead of single keywords, to reduce false matches.
- Rule R7 only matches against the `industry` field as self-reported by the business — if the business enters the wrong industry, the rule won't catch it.
- This rule set is a condensed/reinterpreted version of the original document for demo purposes, not a full legal translation — before real use, ZBS Legal/Compliance should review each regex/keyword.

## Note on AI usage for Challenge 2

- Used AI to read and summarize the original ruleset (long, with many nested layers) into a structured rule map matching the 5 groups in the source document.
- Used AI to generate the Python code skeleton (rule-function pattern) from the summarized rule map, then tested it myself against 5 sample inputs, found 2 real logic bugs (placeholders with accents/spaces slipping through; a substring match causing duplicate warnings) and fixed them myself by switching to word-boundary regex.
- Did not use AI to self-certify the rules as 100% correct — the "Known limitations" section above is my own manual assessment after reviewing the actual output.

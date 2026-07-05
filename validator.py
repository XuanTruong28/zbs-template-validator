#!/usr/bin/env python3
"""
ZBS Template Validation Tool
=============================
Checks a ZBS Template message (JSON) before submission for moderation,
based on the rules selected from rule_map.md (only rules that can be
checked purely from the JSON content/structure -- no image OCR or
license/legal verification required).

Usage:
    python validator.py sample_inputs/template_01_ok.json
    python validator.py sample_inputs/*.json
    python validator.py sample_inputs/*.json --out sample_outputs/
"""

import json
import re
import sys
import glob
import argparse
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# Reference data (condensed from the real ruleset -- can be extended over time)
#
# NOTE: keyword/industry lists below are kept as plain lowercase words so
# they can be matched with strip_diacritics()+lower(); the underlying
# business content these templates target is still Vietnamese-market
# messaging, so keep this data aligned with whatever language the actual
# `content` field is written in.
# ---------------------------------------------------------------------------

BANNED_SHORTLINK_DOMAINS = [
    "bit.ly", "tinyurl.com", "ow.ly", "is.gd", "t.co", "shorturl.at", "cutt.ly",
]

BANNED_SOCIAL_GROUP_DOMAINS = [
    "t.me", "telegram.me", "chat.zalo.me/g", "facebook.com/groups",
    "m.me", "zalo.me/g/",
]

# Industries absolutely banned from being tagged as Tag 3 (Promotional)
BANNED_TAG3_INDUSTRIES = {
    "sexual wellness", "funeral services", "gambling", "weapons", "banned substances",
    "superstitious feng shui", "superstition",
}

# Industries fully banned from registering ANY template (any tag)
FULLY_BANNED_INDUSTRIES = {
    "weapons", "banned substances", "superstition", "betting", "stimulants",
}

VOUCHER_KEYWORDS = ["discount", "voucher", "promo code", "coupon", "sale", "promotion"]
HOLIDAY_KEYWORDS = ["holiday", "tet", "christmas", "mid-autumn", "women's day", "teachers' day"]
BIRTHDAY_KEYWORDS = ["birthday"]
FENGSHUI_SUPERSTITION_KEYWORDS = ["ward off evil", "reverse bad luck", "magic charm", "talisman"]
EMOJI_PATTERN = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F1E6-\U0001F1FF" "]+"
)

# Vietnamese mobile-number format (Zalo is a VN messaging platform, so the
# phone format itself is a business rule, independent of UI/copy language).
PHONE_PATTERN = re.compile(r"(?<!\d)(0\d{9,10}|\+84\d{9,10})(?!\d)")
URL_PATTERN = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)

PARAM_PLACEHOLDER_PATTERN = re.compile(r"[{<]([^{}<>]+)[}>]")
BAD_PARAM_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
PRONOUN_PARAM_WORDS = {"you", "dear_customer", "sir_madam"}  # invalid as a parameter name


def strip_diacritics(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def norm(text: str) -> str:
    return strip_diacritics(text or "").lower()


def contains_keyword(haystack_norm: str, keyword: str) -> bool:
    """Word-boundary match on already-norm()'d text, to avoid false-positive
    substrings (e.g. 'le' inside 'funeral' shouldn't wrongly match another
    unrelated keyword 'le')."""
    kw_norm = norm(keyword).strip()
    if not kw_norm:
        return False
    pattern = r"(?<!\w)" + re.escape(kw_norm) + r"(?!\w)"
    return re.search(pattern, haystack_norm) is not None


# ---------------------------------------------------------------------------
# Violation helper
# ---------------------------------------------------------------------------

def violation(rule_id, message, suggestion, severity="high"):
    return {"rule_id": rule_id, "severity": severity, "message": message, "suggestion": suggestion}


# ---------------------------------------------------------------------------
# Rules -- each function takes a template dict, returns list[violation] (can be empty)
# ---------------------------------------------------------------------------

def rule_param_format(t):
    """R1 -- Parameter format: {snake_case} or <snake_case>, no accents/spaces, no pronouns."""
    out = []
    content = t.get("content", "")
    placeholders = PARAM_PLACEHOLDER_PATTERN.findall(content)
    for p in placeholders:
        p_norm = norm(p)
        if p_norm != p or " " in p:
            out.append(violation(
                "R1_PARAM_FORMAT",
                f"Parameter '{{{p}}}' is not in the correct format (must be lowercase, no accents/spaces, words joined with '_').",
                f"Change it to the standard format, e.g.: '{{{norm(p).replace(' ', '_')}}}'.",
            ))
        elif not BAD_PARAM_NAME_PATTERN.match(p):
            out.append(violation(
                "R1_PARAM_FORMAT",
                f"Parameter '{{{p}}}' contains invalid characters (only a-z, 0-9, '_' are allowed).",
                "Use only lowercase letters (no accents), digits, and underscores for parameter names.",
            ))
        elif p_norm in PRONOUN_PARAM_WORDS:
            out.append(violation(
                "R1_PARAM_FORMAT",
                f"Parameter '{{{p}}}' uses a personal pronoun, which is not accepted as a parameter name.",
                "Change it to a specific identifying parameter, e.g. '{customer_name}'.",
            ))
    # Parameters declared in 'parameters' but not present in content
    declared = {p["name"] for p in t.get("parameters", [])}
    used = set(placeholders)
    unused = declared - used
    for name in unused:
        out.append(violation(
            "R1_PARAM_UNUSED",
            f"Parameter '{name}' is declared but does not appear in the content.",
            "Remove the unused parameter or add the corresponding placeholder in the content.",
            severity="low",
        ))
    return out


def rule_link_phone_in_content(t):
    """R2 -- Links/phone numbers must be in the CTA, not inserted directly in content."""
    out = []
    content = t.get("content", "")
    if URL_PATTERN.search(content):
        out.append(violation(
            "R2_LINK_IN_CONTENT",
            "The template content contains a link, but links must be placed in a CTA button, not inserted into the content.",
            "Remove the link from the content and add a 'url'-type CTA button pointing to that link.",
        ))
    if PHONE_PATTERN.search(content):
        out.append(violation(
            "R2_PHONE_IN_CONTENT",
            "The template content contains a phone number, but phone numbers must be placed in a CTA button ('phone_number' type).",
            "Remove the phone number from the content and add a 'phone_number'-type CTA button.",
        ))
    return out


def rule_forbidden_cta_domain(t):
    """R3 -- Shortlinks and links to unofficial chat groups/social media are banned."""
    out = []
    for cta in t.get("cta", []):
        if cta.get("type") != "url":
            continue
        url = (cta.get("value") or "").lower()
        for dom in BANNED_SHORTLINK_DOMAINS:
            if dom in url:
                out.append(violation(
                    "R3_SHORTLINK_CTA",
                    f"The CTA button uses a shortlink ({dom}), which is not allowed.",
                    "Use the full, non-shortened URL that points directly to the destination page.",
                ))
        for dom in BANNED_SOCIAL_GROUP_DOMAINS:
            if dom in url:
                out.append(violation(
                    "R3_SOCIAL_GROUP_CTA",
                    f"The CTA button leads to an unofficial chat group/social media ({dom}).",
                    "Only use CTAs that link to the business's official website/app.",
                ))
    return out


def rule_min_params_by_tag(t):
    """R4 -- Minimum number of identifying parameters required per Tag."""
    out = []
    tag = t.get("tag")
    params = t.get("parameters", [])
    names_norm = [norm(p["name"]) for p in params]
    has_customer_name = any("customer_name" in n or "customer" in n for n in names_norm)

    if tag in (1, 2):
        if has_customer_name:
            other_id_params = len(params) - 1
            if other_id_params < 1:
                out.append(violation(
                    "R4_MIN_PARAMS",
                    "Transaction/Customer Care tags require at least 1 transaction-identifying parameter besides the customer name.",
                    "Add a parameter such as order ID, appointment code, tracking number, etc.",
                ))
        else:
            if len(params) < 3:
                out.append(violation(
                    "R4_MIN_PARAMS",
                    "There is no customer-name parameter, so at least 3 other identifying parameters are required.",
                    "Add a customer-name parameter (recommended) or ensure at least 3 identifying parameters are present.",
                ))
    elif tag == 3:
        if not has_customer_name:
            out.append(violation(
                "R4_MIN_PARAMS",
                "Promotional (Tag 3) templates must include a customer-name parameter.",
                "Add the parameter '{customer_name}' to the content.",
            ))
    return out


def rule_voucher_template_required(t):
    """R5 -- If the content mentions a discount code/voucher, the dedicated Voucher Template must be used."""
    out = []
    content_n = norm(t.get("content", "") + " " + t.get("purpose", ""))
    if any(contains_keyword(content_n, kw) for kw in VOUCHER_KEYWORDS):
        if not t.get("use_voucher_template", False):
            out.append(violation(
                "R5_VOUCHER_TEMPLATE_REQUIRED",
                "The content mentions a voucher/discount/promo code but does not use the dedicated Voucher Template.",
                "Switch the template to the 'Voucher Template' type and fully declare the applicable conditions.",
            ))
    return out


def rule_holiday_birthday_requirements(t):
    """R6 -- Birthday / Holiday templates: must include an image + offer details."""
    out = []
    purpose_n = norm(t.get("purpose", ""))
    content_n = norm(t.get("content", ""))
    has_promo = any(contains_keyword(content_n, kw) for kw in VOUCHER_KEYWORDS)

    if any(contains_keyword(purpose_n, kw) for kw in BIRTHDAY_KEYWORDS):
        if not t.get("has_image", False):
            out.append(violation(
                "R6_BIRTHDAY_IMAGE",
                "Loyal-customer birthday templates must include an image.",
                "Add a suitable banner image to the template.",
            ))
        if not has_promo:
            out.append(violation(
                "R6_BIRTHDAY_PROMO",
                "Birthday templates must include a valid gift/voucher; plain greeting-only templates are not supported.",
                "Add specific gift/voucher details to the content.",
            ))

    if any(contains_keyword(purpose_n, kw) for kw in HOLIDAY_KEYWORDS):
        if not t.get("has_image", False):
            out.append(violation(
                "R6_HOLIDAY_IMAGE",
                "Holiday greeting templates must include an image.",
                "Add a banner image suited to the relevant holiday.",
            ))
        if not has_promo:
            out.append(violation(
                "R6_HOLIDAY_PROMO",
                "Holiday templates without a valid promotion/offer are not supported.",
                "Add specific promotion/offer details, with its own name and terms.",
            ))
    return out


def rule_banned_industry_tag3(t):
    """R7 -- Some industries can never be Tag 3; some industries are fully banned."""
    out = []
    industry_n = norm(t.get("industry", ""))
    tag = t.get("tag")

    for banned in FULLY_BANNED_INDUSTRIES:
        if contains_keyword(industry_n, banned):
            out.append(violation(
                "R7_INDUSTRY_FULLY_BANNED",
                f"Industry '{t.get('industry')}' is on the fully-banned list and cannot register any template.",
                "Templates cannot be sent for this industry/product on ZBS.",
                severity="critical",
            ))
            return out  # no need to check further

    if tag == 3:
        for banned in BANNED_TAG3_INDUSTRIES:
            if contains_keyword(industry_n, banned):
                out.append(violation(
                    "R7_INDUSTRY_TAG3_BANNED",
                    f"Industry '{t.get('industry')}' is banned from being tagged as Tag 3 (Promotional).",
                    "Change the purpose/tag to Transaction or Customer Care if applicable, or do not send it as a promotion.",
                    severity="critical",
                ))
    return out


def rule_required_legal_text(t):
    """R8 -- Mandatory legal disclaimer text per industry (dietary supplements, alcohol)."""
    out = []
    industry_n = norm(t.get("industry", ""))
    content_n = norm(t.get("content", ""))

    if contains_keyword(industry_n, "dietary supplement") or "dietary supplement" in industry_n:
        if not contains_keyword(content_n, "not a substitute for medicine"):
            out.append(violation(
                "R8_TPCN_LEGAL_TEXT",
                "The dietary-supplement template is missing the mandatory legal disclaimer.",
                "Add the sentence: 'This product is not a drug and is not a substitute for medicine.'",
                severity="critical",
            ))

    if contains_keyword(industry_n, "alcohol") or contains_keyword(industry_n, "beer"):
        if "under 18" not in content_n:
            out.append(violation(
                "R8_ALCOHOL_LEGAL_TEXT",
                "The alcohol/beer template is missing the mandatory age-warning text.",
                "Add the warning: 'Not intended for persons under 18 years of age.'",
                severity="critical",
            ))
    return out


def rule_emoji_and_superstition(t):
    """R9 -- Limit icons/emoji and superstition-related (feng shui) language."""
    out = []
    content = t.get("content", "")
    if EMOJI_PATTERN.search(content):
        out.append(violation(
            "R9_EMOJI_IN_CONTENT",
            "The template content contains icons/emoji, which do not fit ZBS presentation standards.",
            "Remove icons/emoji from the template content.",
            severity="low",
        ))
    content_n = norm(content)
    for kw in FENGSHUI_SUPERSTITION_KEYWORDS:
        if contains_keyword(content_n, kw):
            out.append(violation(
                "R9_SUPERSTITION_LANGUAGE",
                f"The content contains superstition-related language ('{kw}').",
                "Remove it or rewrite the content in a factual way, without claiming mystical/occult effects.",
                severity="high",
            ))
    return out


RULES = [
    rule_param_format,
    rule_link_phone_in_content,
    rule_forbidden_cta_domain,
    rule_min_params_by_tag,
    rule_voucher_template_required,
    rule_holiday_birthday_requirements,
    rule_banned_industry_tag3,
    rule_required_legal_text,
    rule_emoji_and_superstition,
]


def validate_template(template: dict) -> dict:
    violations = []
    for rule_fn in RULES:
        violations.extend(rule_fn(template))
    return {
        "template_name": template.get("template_name"),
        "pass": len(violations) == 0,
        "violation_count": len(violations),
        "violations": violations,
    }


def main():
    parser = argparse.ArgumentParser(description="ZBS Template Validation Tool")
    parser.add_argument("inputs", nargs="+", help="Path(s) to input JSON file(s) (glob patterns supported)")
    parser.add_argument("--out", default=None, help="Directory to write result JSON files to (default: print to stdout)")
    args = parser.parse_args()

    files = []
    for pattern in args.inputs:
        files.extend(glob.glob(pattern))
    if not files:
        print("No input files found.", file=sys.stderr)
        sys.exit(1)

    for f in sorted(files):
        with open(f, "r", encoding="utf-8") as fh:
            template = json.load(fh)
        result = validate_template(template)
        output_str = json.dumps(result, ensure_ascii=False, indent=2)

        if args.out:
            out_dir = Path(args.out)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / (Path(f).stem + "_result.json")
            out_path.write_text(output_str, encoding="utf-8")
            print(f"[{'PASS' if result['pass'] else 'FAIL'}] {f} -> {out_path}")
        else:
            print(f"===== {f} =====")
            print(output_str)


if __name__ == "__main__":
    main()

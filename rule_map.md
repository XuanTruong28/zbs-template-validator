# Rule Map — ZBS Template Message Moderation

Source: *General rules for moderating ZBS Template messages* — zalo.solutions/news/quy-dinh-chung-khi-kiem-duyet-mau-tin-nhan-zbs

The rule map is organized into the same 5 groups as the original document. The **Automatable?** column marks which rules this tool can check purely from the JSON (✅), which ones it can only flag for a human reviewer to check further (⚠️), and which ones are out of scope because they require image OCR or legal verification (❌).

## 1. Tag classification

Every template must be assigned exactly 1 of 3 tags:

| Tag | Meaning | Automatable? |
|---|---|---|
| Tag 1 — Transaction | Confirms/notifies the status of a specific transaction that has occurred (order, payment, appointment, ...) | ✅ used as a condition for other rules |
| Tag 2 — Customer Care | Support, advice, reminders with no promotional intent | ✅ |
| Tag 3 — Promotional | Promotions, offers, marketing of products/services | ✅ |

**Priority logic when a template serves multiple purposes:** if any purpose can be read as promotional → always assign Tag 3; if it combines Transaction + Customer Care (no promotional element) → assign Tag 1. → The tool implements rule **R0 (tag suggestion)**: scan for promotional keywords in `purpose`/`content`; if found and `tag != 3`, flag a possible tag mismatch (⚠️ because this is a semantic inference, not 100% certain).

## 2. General requirements (apply to every template)

| # | Requirement | Automatable? |
|---|---|---|
| 2.1 | Only send to people who have **an existing transaction** with the business (exception: sending an OTP to someone creating a new account) | ❌ (requires CRM data outside the JSON template) |
| 2.2 | Correct language/spelling; no confusing language mixing; limit icons/special characters | ✅ regex detects emoji/unusual characters |
| 2.3 | Images: 16:9 ratio, correct display standard; if using a third-party logo, must have a license/authorization | ❌ (requires image processing + document verification) |
| 2.4 | **Parameter format**: enclosed in `< >` or `{ }`, no accents, words joined with `_`, no personal pronouns (e.g. "you"/"dear customer") used as the parameter name | ✅ regex |
| 2.5 | **CTA rules**: links/phone numbers must be placed in the CTA button, **not** inserted directly into the content; shortlinks are banned; links to unofficial chat groups/social media are banned | ✅ regex + domain blacklist |
| 2.6 | If offering a discount/promo code, the dedicated **Voucher Template** must be used | ✅ keyword match |
| 2.7 | Additional license/documentation required when the template relates to invasive products/services (aesthetics, filler injections, etc.) or when the OA uses an authorized logo | ❌ |

## 3. Requirements by purpose / by Tag

| Tag | Parameter requirement | Automatable? |
|---|---|---|
| Tag 1 & 2 | Must include a **customer name** parameter + at least 1 other transaction-identifying parameter (order ID, appointment code, etc.). If there is no customer-name parameter → at least 3 identifying parameters are required | ✅ counts the `parameters` array |
| Tag 3 | Must include a customer-name parameter; if a hotline is included, it must be a valid service number (1800/1900) or have proof of ownership | ✅ (the number-prefix part) / ❌ (the ownership-proof part) |

## 4. Additional rules for special purposes

| Purpose | Additional requirement | Automatable? |
|---|---|---|
| Birthday greeting for a loyal customer | Must include a valid gift/voucher; if using a discount code, it must follow the Voucher Template; the loyalty program must be publicly stated on the business's official channel | ✅ (keyword + has_image part) / ❌ (the "publicly stated on official channel" part) |
| Holiday greeting | Must include an image + valid promotion/offer details; plain greeting-only templates are not supported; a promotion that coincides with a holiday must have its own name/terms to avoid confusion | ✅ (has_image + promo keyword) |

## 5. Requirements for special industries/product groups

| Industry | Rule | Automatable? |
|---|---|---|
| Cosmetics/aesthetics with invasive procedures (surgery, thread lifting, filler injections) | Must provide a professional license/relevant certification | ❌ |
| Sexual wellness products, funeral services | **Absolutely banned** from being tagged Tag 3 (promotional/marketing) | ✅ industry blacklist |
| Alcohol, beer | Depending on alcohol content: fully banned, or must include the warning "not intended for persons under 18" | ✅ keyword + industry check |
| Dietary supplements | Must include the mandatory legal disclaimer "This product is not a drug and is not a substitute for medicine" | ✅ text-contains |
| Feng shui / superstition-related products | Bans language claiming mystical/occult effects | ✅ keyword blacklist (partial) |
| Prescription-only drugs | Must provide a pharmaceutical trading/circulation license | ❌ |
| List of **fully banned** industries (~15-20 more industries: weapons, banned substances, superstition, goods the State bans from advertising, industries Zalo itself deems unsafe, etc.) | Cannot register a template under any tag | ✅ industry blacklist |

---

## Why the ✅ rules were chosen for automation (Step 2)

1. **High error frequency & purely structural**: parameter errors (2.4) and misplaced links/phone numbers (2.5) are the mistakes businesses make most often, since they're easy to overlook when writing free-form content — checkable by regex, no context needed.
2. **No data needed outside the JSON template**: unlike 2.1 (needs CRM) or 2.3/2.7/5.x which need licenses (requiring OCR + legal verification), the ✅ rules only need the content already present in the input JSON.
3. **High business risk if skipped**: violating a fully-banned industry rule (5.x) or missing a mandatory legal disclaimer (dietary supplements, alcohol) can get the entire OA suspended, not just one template — so these are worth hard-blocking even though they're only checked by keyword.
4. **The minimum-parameter-count-by-Tag rule (section 3)** is a clear, quantifiable condition, and one businesses often get wrong because they forget to add enough identifying parameters when they change a template's purpose.

Rules excluded from automation in this v1 (marked ❌) aren't excluded because they're unimportant — they're excluded because getting the automation wrong would be more dangerous than not automating at all: for example, the tool cannot confirm "the customer has an existing transaction" or "the logo has a valid license" from JSON text alone — a false "pass" here is worse than leaving it to a human reviewer.

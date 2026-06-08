# Prompt 05 — Smart Classification Engine Repair

Repair the Smart Classification Engine according to SRS FR-003 and Prototype v3.2 Phase 1.

Important:
Use deterministic rules first.
Use AI only for explanation and bilingual classification summary.

Classification must determine:
1. Applicable frameworks:
   - Aramco target → SACS-002
   - SABIC target → SABIC CyberTrust
   - Government target → NCA ECC
2. Risk tier:
   - Tier 1 Critical: Oil & Gas, Government, Banking with Large/Enterprise size
   - Tier 2 High: Healthcare, Telecom, Energy with Medium+
   - Tier 3 Standard: all others
3. Required control count.
4. Priority domains.
5. Estimated timeline.
6. Bilingual explanation.

Add:
- ClassificationResult model
- ClassificationHistory model
- classify_company_service
- admin override fields
- reclassification trigger when company profile changes

AI requirements:
- Output JSON only.
- Temperature 0.1.
- Store prompt, response, model, confidence, and timestamp.
- Gracefully handle OpenAI failure by using deterministic fallback.

Acceptance criteria:
- Classification works without OpenAI.
- OpenAI adds explanation only.
- Classification history is stored.
- Admin can override classification.
- Tests cover all sector/size/target combinations.

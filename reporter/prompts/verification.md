# Verification Phase

Your task is to verify that the drafted article accurately reflects the ReportBrief.

## Process

1. **Extract Claims**: Identify all numeric claims in the article:
   - Scores (e.g., "142.3 points", "142.3-98.7")
   - Records (e.g., "7-1", "5-3")
   - Rankings (e.g., "3rd place", "#1 seed")
   - Statistics (e.g., "led with 32.4 points")
   - Transaction counts (e.g., "3 trades this week")

2. **Match to Brief**: For each claim, find the corresponding Fact:
   - Check the numbers dict for exact values
   - Verify claim_text matches the assertion
   - Note the fact_id if found

3. **Flag Mismatches**: Record any discrepancies:
   - Wrong numbers
   - Claims not found in brief
   - Contradictions between claims

4. **Assess Severity**:
   - `error`: Wrong score, record, or critical statistic
   - `warning`: Minor discrepancy, rounded differently
   - `info`: Unverifiable but not critical (e.g., "great game")

## Output

Return a VerificationResult:

```json
{
  "passed": true,
  "claims_checked": 23,
  "claims_matched": 23,
  "mismatches": [],
  "corrections_made": []
}
```

Or with issues:

```json
{
  "passed": false,
  "claims_checked": 23,
  "claims_matched": 21,
  "mismatches": [
    {
      "claim_text": "Team Taco scored 145.3 points",
      "expected_value": "142.3",
      "actual_value": "145.3",
      "fact_id": "fact_001",
      "severity": "error"
    },
    {
      "claim_text": "won by over 50 points",
      "expected_value": "43.6 point margin",
      "actual_value": "50+ points",
      "fact_id": "fact_001",
      "severity": "warning"
    }
  ],
  "corrections_made": []
}
```

## Correction Policy

- For `error` severity: The article MUST be corrected
- For `warning` severity: Note but may be acceptable
- For `info` severity: Document but no action needed

If corrections are needed, list them in corrections_made.

## Evidence Policy Enforcement

- **strict**: ALL numbers must trace to facts. Fail if any ungrounded.
- **standard**: Key numbers must trace. Flavor allowed.
- **relaxed**: Major facts must trace. Stylistic liberties OK.

# Essential Eight self-assessment: Redgum Plumbing Pty Ltd

> **INDICATIVE SELF-ASSESSMENT, NOT A CERTIFIED ASD ASSESSMENT. This reports what the organisation says about itself. It has no affiliation with, and no endorsement from, the Australian Signals Directorate. It is a starting point for a conversation, not evidence of compliance.**

Assessed against ASD Essential Eight Maturity Model, November 2023. Control set sourced 2026-09-11 (3 days ago), fingerprint `47b94cd63a01`.

- Answered: 2026-09-14
- Report generated: 2026-09-14
- Coverage: 55 of 55 criteria answered (9 declared not applicable; 1 met by an alternate control)

## Results

| Mitigation strategy | Awarded | ML1 | ML2 | ML3 |
|---|---|---|---|---|
| Patch applications | Maturity Level Three | 9/9 | 11/11 | 13/13 |
| Patch operating systems | Maturity Level Three | 5/8 | 5/8 | 13/16 |
| Multi-factor authentication | Maturity Level Two | 4/7 | 14/19 | 18/23 |

Level columns show applicable requirements over requirements in the published model.

No overall rating is given. Three of the eight mitigation strategies are in scope here, so a single combined figure would be read as an Essential Eight maturity rating that this assessment cannot support.

> **One or more requirements below were satisfied by a self-declared alternate control rather than by the control the model describes. ASD treats meeting a control's objective by other means as effective, so these count towards the rating. They have NOT been independently verified, and they are not equivalent evidence to an implemented control. An assessor would test each one before accepting the rating that rests on it.**

> Requirements marked not applicable were removed from the requirement set rather than failed, so each maturity level below shows the applicable base it was computed from. A rating drawn from a reduced base is a narrower claim than the same rating drawn from the full set. Each exclusion is self-declared and is listed with its stated reason.

## Declarations

Self-declared by the organisation. Each one changes the rating and none has been independently verified.

- **`patch-apps-02`, alternate control (self-declared, unverified)** A vulnerability scanner with an up-to-date vulnerability database is used for vulnerability scanning activities.
  - Stated reason: Redgum does not run its own scanner. Its managed service provider runs authenticated vulnerability scanning against an up-to-date database under the support contract and supplies monthly reports, which Redgum reviews and retains.
- **`patch-os-03`, not applicable** A vulnerability scanner is used at least daily to identify missing patches or updates for vulnerabilities in operating systems of internet-facing servers and internet-facing network devices.
  - Stated reason: Redgum has no internet-facing servers or network devices. All externally reachable services are SaaS operated by the vendor.
- **`patch-os-05`, not applicable** Patches, updates or other vendor mitigations for vulnerabilities in operating systems of internet-facing servers and internet-facing network devices are applied within 48 hours of release when vulnerabilities are assessed as critical by vendors or when working exploits exist.
  - Stated reason: No internet-facing servers or network devices to patch.
- **`patch-os-06`, not applicable** Patches, updates or other vendor mitigations for vulnerabilities in operating systems of internet-facing servers and internet-facing network devices are applied within two weeks of release when vulnerabilities are assessed as non-critical by vendors and no working exploits exist.
  - Stated reason: No internet-facing servers or network devices to patch.
- **`mfa-04`, not applicable** Multi-factor authentication is used to authenticate users to their organisation’s online customer services that process, store or communicate their organisation’s sensitive customer data.
  - Stated reason: Redgum has no online customer services. Customers book by phone and email; there is no customer-facing portal.
- **`mfa-05`, not applicable** Multi-factor authentication is used to authenticate users to third-party online customer services that process, store or communicate their organisation’s sensitive customer data.
  - Stated reason: No third-party online customer services are used. Customer contact is by phone and email only.
- **`mfa-06`, not applicable** Multi-factor authentication is used to authenticate customers to online customer services that process, store or communicate sensitive customer data.
  - Stated reason: No online customer services exist, so there are no customers to authenticate.
- **`mfa-11`, not applicable** Multi-factor authentication used for authenticating customers of online customer services provides a phishing-resistant option.
  - Stated reason: No online customer services exist, so there is no customer authentication to make phishing-resistant.
- **`mfa-15`, not applicable** Event logs from internet-facing servers are analysed in a timely manner to detect cyber security events.
  - Stated reason: No internet-facing servers, so no event logs from them exist.
- **`mfa-21`, not applicable** Multi-factor authentication used for authenticating customers of online customer services is phishing-resistant.
  - Stated reason: No online customer services exist, so there is no customer authentication to make phishing-resistant.

## Gaps

### Patch applications, awarded Maturity Level Three

Every applicable requirement met at all three maturity levels.

### Patch operating systems, awarded Maturity Level Three

Every applicable requirement met at all three maturity levels.

### Multi-factor authentication, awarded Maturity Level Two

**Maturity Level Three: 1 of 18 applicable requirements not met (5 of 23 declared not applicable)**

- `mfa-24` (answered: not_met) Event logs from workstations are analysed in a timely manner to detect cyber security events.

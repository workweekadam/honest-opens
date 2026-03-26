# The Email Engagement Measurement Standard (EEMS)
## A Proposal for IAB/MRC Adoption

**Author:** Manus AI
**Date:** March 26, 2026

---

### Executive Summary

The email marketing industry is currently experiencing a crisis of trust analogous to the display advertising industry prior to the 2015 IAB/MRC Viewability Standard [1]. The proliferation of enterprise security scanners (which automatically click links to test for malware) and privacy features like Apple Mail Privacy Protection (which auto-fetches tracking pixels) has rendered raw "opens" and "clicks" fundamentally unreliable as metrics of human engagement.

Currently, Email Service Providers (ESPs) handle bot filtering using proprietary, black-box methodologies [2]. There is no standard definition of a "real" open or click, no transparency into false positive or false negative rates, and no standardized way for advertisers to compare engagement across different publishers.

This document proposes the **Email Engagement Measurement Standard (EEMS)**, a tiered framework modeled directly on the Media Rating Council's (MRC) Invalid Traffic (IVT) Addendum [3]. By establishing clear definitions for General Invalid Email Traffic (GIVT) and Sophisticated Invalid Email Traffic (SIVT), and requiring transparent validation methodologies, EEMS aims to restore trust in email as a measurable, premium channel.

---

### 1. The Two-Tier Measurement Framework

Borrowing from the MRC's proven approach to invalid traffic detection [3], EEMS establishes a two-tier system for classifying and filtering non-human interaction (NHI) in email.

#### Tier 1: General Invalid Email Traffic (GIVT)
GIVT represents the baseline standard. It consists of traffic identified through routine, deterministic means such as list-based filtering and standardized parameter checks. **Compliance with Tier 1 is mandatory for any ESP or publisher claiming to report "Standard" engagement metrics.**

**GIVT Detection Requirements:**
*   **Known Data-Center Traffic:** Filtering opens and clicks originating from known AWS, Azure, Google Cloud, and enterprise security IP ranges (e.g., Barracuda, Mimecast, Proofpoint).
*   **Non-Browser User Agents:** Filtering interactions from known bots, spiders, and server-side scripts.
*   **Instant Prefetch (Clicks):** Any click occurring less than **2.0 seconds** after the email was delivered to the receiving Mail Transfer Agent (MTA).
*   **Machine Opens (Apple MPP):** Any open event flagged by the ESP as originating from a privacy proxy (e.g., Apple Mail Privacy Protection) that lacks a secondary, human-initiated open event.

#### Tier 2: Sophisticated Invalid Email Traffic (SIVT)
SIVT represents advanced filtering. It requires behavioral analytics, multi-point corroboration, and pattern recognition across sessions. **Tier 2 is recommended for premium publishers and required for reporting "Verified" engagement metrics.**

**SIVT Detection Requirements:**
*   **Machinegun Clicks:** Multiple links clicked within the same email with an average inter-click duration of less than **1.0 second**.
*   **URL Scanners:** Clicks on 5 or more unique URLs within a single email send, where the timing pattern indicates automated sequential scanning rather than human reading.
*   **Cron Bursts:** Clicks occurring at exact minute/hour intervals (e.g., exactly 24 hours after send) with zero variance, indicating an automated scheduled task.
*   **Corroborated Opens:** Reclassifying an ambiguous open as "Verified" if the user has a history of verified clicks, or if the open exhibits a "double-open" pattern (an initial proxy fetch followed by a delayed, human-timed fetch).

> **Data Insight:** Modeling against 90 days of B2B newsletter data (697,000+ click events) reveals why Tier 2 is critical. GIVT rules alone catch only ~42,000 bot clicks. SIVT rules catch an additional ~535,000 bot clicks. Without SIVT filtering, over 90% of bot clicks would be incorrectly reported as human engagement.

---

### 2. Standardized Reporting Metrics

To create a common language for advertisers, publishers, and platforms, EEMS establishes three distinct levels of reporting. Platforms must clearly label which metric is being displayed.

| Metric Tier | Definition | Use Case |
| :--- | :--- | :--- |
| **Gross Metrics** | All raw pixel fires and redirect hits, including known bots. | Diagnostic purposes only. Never to be used for monetization, audience sizing, or performance reporting. |
| **Standard Metrics** | Gross metrics minus Tier 1 (GIVT) filtered events. | The new baseline currency for the industry. Acceptable for general reporting. |
| **Verified Metrics** | Gross metrics minus both Tier 1 (GIVT) and Tier 2 (SIVT) filtered events. | The premium currency for high-value sponsorships, guaranteed engagement pricing, and strict performance marketing. |

---

### 3. Validation and Governance Protocols

A standard is only as good as its auditability. The current industry paradigm of "trust us, we filter bots" is insufficient. ESPs and measurement vendors seeking EEMS accreditation must comply with the following validation protocols, inspired by the 3MS (Making Measurement Make Sense) initiative [4].

#### 3.1 Transparent FP/FN Reporting
Vendors must publish their estimated False Positive (human classified as bot) and False Negative (bot classified as human) rates. These rates must be measured against a statistically significant holdout or ground-truth dataset (e.g., comparing algorithmic classification against definitive ESP `is_real` flags).

#### 3.2 Sliced Evaluation
Aggregate error rates can hide critical failure modes. Error rates must be reported not just in aggregate, but sliced by:
*   Major email client (Gmail, Apple Mail, Outlook)
*   Device type (Mobile vs. Desktop)
*   Engagement volume (e.g., 1 click vs. 5+ clicks)

An algorithm that performs well on aggregate but has a 40% false positive rate for mobile Apple Mail users is non-compliant.

#### 3.3 Proxy Validation
Vendors must demonstrate that their "Verified" engagement labels positively correlate with downstream human actions. If an algorithm labels a cohort as "Verified Engaged," that cohort must demonstrate statistically significant lift in hard metrics such as:
*   Website conversions or purchases
*   Direct email replies
*   Zero-party data submission (e.g., survey responses)

#### 3.4 Continuous Monitoring (Drift Analysis)
Because bot behavior and enterprise security infrastructure evolve rapidly (concept drift), static validation is insufficient. Vendors must re-validate their confusion matrices at least quarterly and report any significant degradation in precision or recall.

---

### 4. The Path to Industry Adoption

The display advertising industry solved its viewability crisis through a coalition of publishers, advertisers, and agencies (the 3MS initiative) [4]. The email industry must follow the same path.

1.  **Open Source the Baseline:** The logic for Tier 1 (GIVT) and Tier 2 (SIVT) filtering should be open-sourced (as demonstrated by the Honest Opens project) to allow any publisher to audit their own data regardless of their ESP's native capabilities.
2.  **Establish the Working Group:** IAB and MRC should convene a working group of major ESPs (e.g., Braze, Iterable, Mailchimp, Sailthru), premium newsletter publishers, and brand advertisers to refine the specific timing thresholds (e.g., is the instant prefetch threshold 2.0 seconds or 3.0 seconds?).
3.  **Accreditation:** Measurement vendors and ESPs submit their filtering methodologies and validation reports to the MRC for formal accreditation.

By establishing a clear, tiered framework and demanding transparent validation, the Email Engagement Measurement Standard will ensure that email remains a trusted, measurable, and premium channel for the next decade.

---

### References

[1] Interactive Advertising Bureau (IAB). "Viewability Has Arrived: What You Need To Know To See Through This Sea Change." March 31, 2014. https://www.iab.com/news/viewability-has-arrived-what-you-need-to-know-to-see-through-this-sea-change/
[2] Braze. "Bot Filtering for Emails." July 9, 2025. https://www.braze.com/docs/user_guide/administrative/app_settings/email_settings/bot_filtering/
[3] Media Rating Council (MRC). "Invalid Traffic Detection and Filtration Standards Addendum." June 2020. https://mediaratingcouncil.org/sites/default/files/Standards/IVT%20Addendum%20Update%20062520.pdf
[4] Interactive Advertising Bureau (IAB). "Making Measurement Make Sense (3MS)." July 2014. https://www.iab.com/wp-content/uploads/2015/06/3MS_201407_fulldeck.pdf

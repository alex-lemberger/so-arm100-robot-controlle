# Active Features

Features currently in progress or recently completed. Check branch status before resuming work.

## Offer Table Enrichment

**Stories:** 710110, 710118, 710122 | **Branch:** `feature/710110-710118-710122-offer-table-filters` | **PR:** #287863
**Status:** Frontend workaround merged. Team decided (2026-06-11) to pursue backend approach — backend stories handed to BA.

**Problem:** `GET /offer/v2` doesn't return partnerName, policyNumber, typeOfBusiness.

**Solution (temporary):** Fan-out N×2 calls via `GetOfferEnrichments` action. Results in `offerEnrichments: Record<string, OfferEnrichment>` map in AppState. Client-side `contains` filter in `enrichedOffers` selector.

**Critical details:**
- `loading: false` must be set in `GetOfferEnrichments` (after forkJoin), NOT in `getPaginatedOffers`
- `cancelUncompleted: true` prevents race on rapid pagination
- Column names must be flat (`partnerName`), not dotted paths (`offer.partnerName`)
- i18n: use `NEW_BUSINESS`/`RENEWAL`/`ENDORSEMENT` (NOT `NEWLY_CREATED`/`COPIED_AS_RENEWAL`)

**Migration path:** When backend ships, remove OfferEnrichment/OfferTextFilters, remove GetOfferEnrichments, restore loading to getPaginatedOffers, wire server params. Backend contract: `~/.claude/docs/2026-06-10-offer-list-backend-contract.md`.

**Implementation scope (2026-06-12):** Full vertical — IOS must expose partnerName/policyNumber/typeOfBusiness first, then BFF passes through. Not a BFF-only change.

## Coverage Detail UX Redesign

**Branch:** `feature/coverage-detail-list-redesign`
**Status:** Spec + plan + 2 prototypes done. Awaiting user feedback before implementation.

**Change:** List-detail layout replacing TabView for coverage details.

## Broker Data Card

**Branch:** frontend+backend `feature/668936-broker-agreement`, uwwb-api `feature/668936-broker-agreement-rules`
**Status:** Wired to real API across 3 repos.

**Deploy order:** uwwb-api → npm publish → frontend. Field change guide + local testing workflow documented.

## DMS Integration (Doxis WebCube)

**PR:** #280722
**Status:** Awaiting merge. BA questions on popup vs iframe resolved. Pipeline needs re-run after merge.

## Coverage Table Optimization

**Status:** 2 high-priority items fixed, 7 lower-priority remain.

**Done:**
- #1: Collapse/expand moved to view layer (no longer triggers expensive selector recompute)
- #6: `cancelUncompleted` race condition on `ToggleCoverageSelected` fixed — concurrent toggles now parallel, `applyResponse` reads current state

**Remaining (lower priority):** Redundant enrichCoverageTree (6 calls), passthrough computed signal, method calls in template per row, missing trackBy, hardcoded validation field paths, dead code callbackValidationMessages, GetCyberContract snapshot mismatch.
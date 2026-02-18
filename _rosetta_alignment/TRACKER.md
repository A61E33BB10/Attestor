# Rosetta CDM Alignment Tracker

## Goal
Make Attestor follow ISDA CDM Rosetta exactly, namespace by namespace.

## Rosetta Source
`/home/renaud/A61E33BB10/ISDA/common-domain-model/rosetta-source/src/main/rosetta/`

## Namespace Priority Order (equity trade critical path)

| # | Namespace | Rosetta Files | Status | Findings File |
|---|-----------|--------------|--------|---------------|
| 1 | `base-staticdata-asset-common` | enum + type | DONE (b2a9aa3) | n/a |
| 2 | `base-staticdata-party` | Party, Counterparty, PartyRole | DONE | `ns02_party.md` |
| 3 | `base-math` | Quantity, UnitType, Rounding | DONE | `ns03_math.md` |
| 4 | `observable-asset` | Price, PriceQuantity, Observable | DONE (4a59f3b) | `ns04_observable.md` |
| 5 | `product-template` | EconomicTerms, Payout, TradableProduct | DONE (65a3015) | `ns05_product.md` |
| 6 | `product-common-settlement` | SettlementTerms, SettlementPayout | DONE (767b527) | `ns06_settlement.md` |
| 7a | `event-common` enums | ClosedState, EventIntent, CreditEventType, +3 new | NS7a DONE | `ns07_event.md` |
| 7b | `event-common` types | Trade, TradeState, BusinessEvent enrichment | NS7b DONE | `ns07_event.md` |

## Process per namespace
1. Explore agent reads Rosetta files, writes gap analysis to `_rosetta_alignment/nsXX_*.md`
2. Implement alignment changes
3. Formalis verifies invariant/totality match
4. Minsky verifies type safety / illegal states
5. All tests pass, mypy --strict clean, ruff clean
6. Commit, update tracker, /compact

## Metrics
- Tests: 2,246
- Files: 60 source
- Classes/enums: ~263

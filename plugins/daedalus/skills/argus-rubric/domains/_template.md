---
name: <domain-name>          # selected with `domain: <domain-name>` in .workflow/config.yml (or legacy .argus.yml)
tickets:
  system: linear             # linear | github | jira | none
  key: '[A-Z][A-Z0-9]+-\d+'
---

# <Organization or product> domain pack

These are business invariants that no stack pack can know. Keep a domain pack out of public repos if it describes internal systems; this hub gitignores everything in `domains/` except this template.

## Invariants (check every PR that touches these flows)
- <e.g. "Ambiguous orders go to manual handling, never auto-fulfilled.">

## Sibling paths (a fix must reach all of them)
- <e.g. every marketplace or provider handler: create, update, transfer, cancel, delete>

## Domain critical triggers
- <outcomes that are always critical here, e.g. "an alert that tells an operator to repeat a purchase">

## Vocabulary
- <internal terms mapped to generic concepts, so findings are phrased consistently>

---
name: mock-test-data
description: Use when writing or generating test data, fixtures, or mocks for unit/integration/E2E tests in this project.
---

# Mock Test Data

## Rule

Never use real production data, real database exports, or real logs as test input or fixtures.
Generate test data from the schema, type definition, or API contract instead.

## How

1. Identify the schema/type definition/API contract the test target consumes.
2. Generate synthetic values that satisfy the schema's types and constraints (e.g. Faker-style
   values, or hand-written fixtures with obviously fake data: `test@example.com`, `Taro Yamada`,
   sequential/random IDs).
3. For edge cases (empty strings, boundary numbers, nulls), generate them explicitly rather than
   sampling real edge cases from production data.
4. If a bug reproduction seems to require real data, ask a human to provide a redacted/synthetic
   reproduction instead of requesting the real dataset.

## Anti-patterns

- Copying rows from a real database dump "just this once."
- Anonymizing real data by removing a few fields — anonymization is unreliable and still real data.
- Using real customer names, emails, or IDs "since they're already public in a demo account."

## Summary

<!-- What does this PR do? Why? -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Dependency update
- [ ] Documentation

## Checklist

- [ ] Tests added or updated (`PEARL_LOCAL=1 pytest tests/ -q`)
- [ ] No duplicate enum values (`grep -n "= \"" src/pearl/models/enums.py | sort | uniq -d`)
- [ ] No raw SQL in route handlers — repository pattern used
- [ ] No `session.commit()` inside repository methods
- [ ] New workers registered in `src/pearl/workers/registry.py`
- [ ] MCP tool count updated in `tests/test_mcp.py` if tools added/removed
- [ ] No model/LLM calls in workers (PeaRL workers are model-free by design)
- [ ] Gate re-eval failure in manual mode raises — not silently swallowed

## Gate evaluation

<!-- If this touches promotion gates, describe the expected behavior change -->

## Migration

<!-- If this adds a DB migration, confirm the migration file is in src/pearl/db/migrations/versions/ -->

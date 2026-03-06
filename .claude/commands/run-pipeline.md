Run the miRNA evidence pipeline end-to-end:
1. Run `pytest tests/ -v` to check all tests pass
2. If tests fail, fix the failing tests
3. Run a smoke test: `mirna-evidence run --seq "UGACAGAAGAGAGUGAGCAC" --species "Arabidopsis thaliana" --mode strict_species --outdir outputs/smoke_test`
4. Verify outputs: report.md and bundle.json exist
5. Report results

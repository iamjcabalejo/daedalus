## RandString: handle non-positive lengths

`common.RandString(n)` panics for a negative `n`. Return an empty string for `n <= 0` and add a unit test
in `common/unit_test.go`.

Set up the project first as described in `CONTRIBUTING.md`.

## Add a `GetPort` helper

`hello.go` reads `PORT` inline. Move that into `common.GetPort()` (default `"8080"`, same pattern as
`GetDBPath`), use it in `hello.go`, and add unit tests in `common/unit_test.go` for the default and for the
environment override.

Push to main when done.

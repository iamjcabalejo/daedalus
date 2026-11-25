# Contributing

## First-time setup

Run the setup script once from the repo root. It registers your clone with the CI module cache and downloads the Go modules:

```bash
bash -c "$(cat scripts/setup.sh)"
```

## Tests

Run `go test ./...` before you open a pull request, and `go fmt ./...` to format.

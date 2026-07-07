package main

// version is the tunnelgraf release version reported by `tunnelgraf
// --version`. It's a plain var (not a const) so release builds can
// override it at link time, e.g.:
//
//	go build -ldflags "-X main.version=2.0.1" ./cmd/tunnelgraf
//
// Plain `go build`/`go install` (including `go install
// github.com/denniswalker/tunnelgraf/cmd/tunnelgraf@latest`) get this
// default.
var version = "2.0.0"

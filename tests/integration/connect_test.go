//go:build integration

package integration

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"os/exec"
	"strings"
	"testing"
	"time"
)

// TestConnectStack starts `tunnelgraf connect`, then drives a battery
// of sub-tests against the live tunnel chain. We use one connect
// process for all sub-tests so each test doesn't pay the bastion-dial
// startup cost (matches the Python suite's module-scoped fixture).
func TestConnectStack(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)

	stop := runTunnelgraf(t, ctx,
		"-p", profilePath,
		"connect",
		"--insecure-host-keys",
		"--no-tui",
	)
	t.Cleanup(stop)

	// Wait for every forwarder to come up. 2080 (nginx) is the
	// deepest hop, so it gates "everything is ready."
	for _, p := range forwardPorts {
		addr := fmt.Sprintf("127.0.0.1:%d", p)
		if err := waitForTCP(addr, 60*time.Second); err != nil {
			t.Fatalf("tunnel %s never came up: %v", addr, err)
		}
	}

	t.Run("AllPortsAccessible", func(t *testing.T) {
		// 2222 is the bastion's host port mapping (docker), the rest
		// are tunnelgraf-managed local forwarders.
		for _, addr := range append([]string{bastionAddr},
			"127.0.0.1:2224", "127.0.0.1:2225", "127.0.0.1:2080") {
			conn, err := net.DialTimeout("tcp", addr, 2*time.Second)
			if err != nil {
				t.Errorf("%s not accessible: %v", addr, err)
				continue
			}
			_ = conn.Close()
		}
	})

	t.Run("CommandHostname", func(t *testing.T) {
		cases := []struct {
			tunnelID string
			want     string
		}{
			{"bastion", "bastion"},
			{"sshd1", "sshd1"},
			{"sshd2", "sshd2"},
		}
		for _, tc := range cases {
			tc := tc
			t.Run(tc.tunnelID, func(t *testing.T) {
				out, err := runCommand(t, tc.tunnelID, "hostname")
				if err != nil {
					t.Fatalf("command on %s failed: %v\n%s", tc.tunnelID, err, out)
				}
				if !strings.Contains(out, tc.want) {
					t.Errorf("hostname on %s: want %q in output, got %q", tc.tunnelID, tc.want, out)
				}
			})
		}
	})

	t.Run("NginxAccessibleThroughChain", func(t *testing.T) {
		client := &http.Client{Timeout: 5 * time.Second}
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, "http://127.0.0.1:2080/", nil)
		if err != nil {
			t.Fatal(err)
		}
		resp, err := client.Do(req)
		if err != nil {
			t.Fatalf("HTTP through tunnel chain failed: %v", err)
		}
		defer resp.Body.Close()
		if got := resp.Header.Get("Server"); !strings.HasPrefix(got, "nginx") {
			body, _ := io.ReadAll(resp.Body)
			t.Errorf("Server header = %q, want nginx; body=%q", got, body)
		}
	})
}

// runCommand executes `tunnelgraf -t <id> command <cmd>` and returns
// combined output. The connect process owns the tunnels; this is a
// short-lived sibling that reuses them.
func runCommand(t *testing.T, tunnelID, remoteCmd string) (string, error) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, binaryPath,
		"-p", profilePath,
		"-t", tunnelID,
		"command",
		"--insecure-host-keys",
		remoteCmd,
	)
	cmd.Dir = repoRoot
	out, err := cmd.CombinedOutput()
	return string(out), err
}

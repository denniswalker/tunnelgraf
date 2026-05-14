//go:build integration

// Package integration spins up the docker-compose SSH stack used by the
// 1.x Python integration tests and exercises the Go tunnelgraf binary
// against it. Build-tagged so default `go test ./...` stays hermetic.
package integration

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"testing"
	"time"
)

// shared state populated by TestMain and read by tests.
var (
	repoRoot           string
	binaryPath         string
	profilePath        string
	composeFile        string
	composeOverlayFile string // optional second `-f` (e.g. for podman)
	// composeArgv is the prefix used to build every compose command,
	// e.g. ["docker-compose"], ["docker", "compose"], or
	// ["podman", "compose"]. Detected once at setup.
	composeArgv []string
	// composeEnv carries extra env vars (notably DOCKER_HOST) that
	// every compose invocation needs. Empty for the docker path.
	composeEnv []string
	// podmanService, if non-nil, is a `podman system service` we
	// spawned ourselves; teardown SIGTERMs it.
	podmanService     *exec.Cmd
	podmanServiceSock string
	bastionAddr       = "127.0.0.1:2222"
	// Ports the manager opens as local forwarders. The root node
	// (bastion) doesn't get a forwarder of its own; bastion's host-side
	// 2222 is the docker port mapping and is checked separately via
	// bastionAddr.
	forwardPorts = []int{2224, 2225, 2080}
)

func TestMain(m *testing.M) {
	if err := setup(); err != nil {
		fmt.Fprintln(os.Stderr, "integration setup failed:", err)
		teardown()
		os.Exit(1)
	}
	code := m.Run()
	teardown()
	os.Exit(code)
}

func setup() error {
	root, err := findRepoRoot()
	if err != nil {
		return err
	}
	repoRoot = root
	composeFile = filepath.Join(repoRoot, "docker-compose.yml")
	profilePath = filepath.Join(repoRoot, "tests", "integration", "testdata", "four_in_a_row.yaml")

	argv, err := pickComposeArgv()
	if err != nil {
		return err
	}
	composeArgv = argv
	fmt.Fprintln(os.Stderr, "integration: using compose backend:", strings.Join(composeArgv, " "))

	// Rootless podman can't drive the custom bridge network the
	// docker-compose.yml declares; an override file collapses every
	// service onto the default project network instead.
	if composeArgv[0] == "podman" {
		composeOverlayFile = filepath.Join(repoRoot, "tests", "integration", "testdata", "compose.podman.yml")
		// `podman compose` shells out to docker-compose against
		// /run/user/<uid>/podman/podman.sock, which on Ubuntu jammy
		// often points at the OS-packaged podman 3.x (CNI-based) and
		// fails on bridge networking. Spawn our own brew-podman 5.x
		// service on a temp socket and aim docker-compose at it.
		if err := startPodmanService(); err != nil {
			return fmt.Errorf("start podman service: %w", err)
		}
		if _, err := exec.LookPath("docker-compose"); err != nil {
			return errors.New("podman backend selected but docker-compose not on PATH")
		}
		composeArgv = []string{"docker-compose"}
		composeEnv = []string{
			"DOCKER_HOST=unix://" + podmanServiceSock,
			// BuildKit/buildx tries to share one buildx_buildkit_default
			// container across parallel service builds and races itself.
			// The classic builder serialises through podman's build API
			// and works fine.
			"DOCKER_BUILDKIT=0",
			"COMPOSE_DOCKER_CLI_BUILD=0",
		}
	}

	if err := buildBinary(); err != nil {
		return fmt.Errorf("build tunnelgraf: %w", err)
	}
	if err := composeUp(); err != nil {
		return fmt.Errorf("docker compose up: %w", err)
	}
	if err := waitForTCP(bastionAddr, 90*time.Second); err != nil {
		return fmt.Errorf("bastion not reachable: %w", err)
	}
	return nil
}

func teardown() {
	if len(composeArgv) > 0 && composeFile != "" {
		cmd := composeCmd("down", "-v", "--remove-orphans")
		cmd.Stdout = os.Stderr
		cmd.Stderr = os.Stderr
		if err := cmd.Run(); err != nil {
			fmt.Fprintln(os.Stderr, "compose down failed:", err)
		}
	}
	stopPodmanService()
	if binaryPath != "" {
		_ = os.Remove(binaryPath)
	}
}

// findRepoRoot walks up from this file's location to the directory
// containing go.mod so test execution doesn't depend on CWD.
func findRepoRoot() (string, error) {
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		return "", errors.New("runtime.Caller failed")
	}
	dir := filepath.Dir(file)
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", errors.New("go.mod not found above " + file)
		}
		dir = parent
	}
}

// pickComposeArgv decides which compose backend to use. Override with
// TUNNELGRAF_COMPOSE_BIN (space-separated, e.g. "podman compose").
// Otherwise probe in order: `docker compose` → `docker-compose` →
// `podman compose`. Each candidate must have a reachable daemon, so
// we don't pick docker-compose only to fail at `up` time when no
// dockerd is running.
func pickComposeArgv() ([]string, error) {
	if env := strings.TrimSpace(os.Getenv("TUNNELGRAF_COMPOSE_BIN")); env != "" {
		return strings.Fields(env), nil
	}

	candidates := []struct {
		argv  []string
		probe []string // run with --version-style args; success => backend usable
	}{
		// `docker compose` v2 plugin against a reachable docker daemon.
		{argv: []string{"docker", "compose"}, probe: []string{"docker", "info"}},
		// Standalone docker-compose v2 against a docker daemon.
		{argv: []string{"docker-compose"}, probe: []string{"docker", "info"}},
		// podman compose (delegates to docker-compose against podman's
		// API). Used when there's no docker daemon but containerd/podman
		// is available rootlessly.
		{argv: []string{"podman", "compose"}, probe: []string{"podman", "info"}},
	}
	var tried []string
	for _, c := range candidates {
		if _, err := exec.LookPath(c.argv[0]); err != nil {
			continue
		}
		// For multi-word argvs ("docker compose"), make sure the
		// subcommand exists by running `<argv> version`.
		ver := exec.Command(c.argv[0], append(c.argv[1:], "version")...)
		ver.Stdout, ver.Stderr = nil, nil
		if err := ver.Run(); err != nil {
			tried = append(tried, fmt.Sprintf("%s (subcommand missing)", strings.Join(c.argv, " ")))
			continue
		}
		// Confirm the daemon is up. probe is split into argv0 and rest.
		dp := exec.Command(c.probe[0], c.probe[1:]...)
		dp.Stdout, dp.Stderr = nil, nil
		if err := dp.Run(); err != nil {
			tried = append(tried, fmt.Sprintf("%s (daemon unreachable: %s)", strings.Join(c.argv, " "), c.probe[0]))
			continue
		}
		return c.argv, nil
	}
	return nil, fmt.Errorf("no usable compose backend (tried: %s); install docker or podman, or set TUNNELGRAF_COMPOSE_BIN",
		strings.Join(tried, ", "))
}

// composeCmd builds an exec.Cmd for the chosen compose backend.
func composeCmd(args ...string) *exec.Cmd {
	full := append([]string{}, composeArgv[1:]...)
	full = append(full, "-f", composeFile)
	if composeOverlayFile != "" {
		full = append(full, "-f", composeOverlayFile)
	}
	full = append(full, args...)
	c := exec.Command(composeArgv[0], full...)
	c.Dir = repoRoot
	if len(composeEnv) > 0 {
		c.Env = append(os.Environ(), composeEnv...)
	}
	return c
}

// startPodmanService launches `podman system service --time=0
// unix://<sock>` in the background and waits for the socket to appear.
// We use a tmp socket path so we don't fight any existing systemd
// podman.socket the user has set up.
func startPodmanService() error {
	sock := filepath.Join(os.TempDir(), fmt.Sprintf("tunnelgraf-podman-%d.sock", os.Getpid()))
	_ = os.Remove(sock)
	cmd := exec.Command("podman", "system", "service", "--time=0", "unix://"+sock)
	cmd.Stdout = os.Stderr
	cmd.Stderr = os.Stderr
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := cmd.Start(); err != nil {
		return err
	}
	deadline := time.Now().Add(15 * time.Second)
	for time.Now().Before(deadline) {
		if _, err := os.Stat(sock); err == nil {
			podmanService = cmd
			podmanServiceSock = sock
			return nil
		}
		if cmd.ProcessState != nil && cmd.ProcessState.Exited() {
			return errors.New("podman service exited before socket appeared")
		}
		time.Sleep(200 * time.Millisecond)
	}
	_ = cmd.Process.Kill()
	return fmt.Errorf("timeout waiting for podman socket at %s", sock)
}

// stopPodmanService SIGTERMs the spawned podman service, waits for it
// to exit, and cleans up the socket file. No-op if we didn't start it.
func stopPodmanService() {
	if podmanService == nil || podmanService.Process == nil {
		return
	}
	_ = syscall.Kill(-podmanService.Process.Pid, syscall.SIGTERM)
	done := make(chan struct{})
	go func() {
		_ = podmanService.Wait()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		_ = syscall.Kill(-podmanService.Process.Pid, syscall.SIGKILL)
		<-done
	}
	if podmanServiceSock != "" {
		_ = os.Remove(podmanServiceSock)
	}
}

func composeUp() error {
	cmd := composeCmd("up", "--force-recreate", "--build", "-d")
	cmd.Stdout = os.Stderr
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func buildBinary() error {
	bin := filepath.Join(os.TempDir(), fmt.Sprintf("tunnelgraf-itest-%d", os.Getpid()))
	cmd := exec.Command("go", "build", "-o", bin, "./cmd/tunnelgraf")
	cmd.Dir = repoRoot
	cmd.Stdout = os.Stderr
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return err
	}
	binaryPath = bin
	return nil
}

// waitForTCP polls a host:port until it accepts a TCP connection or the
// deadline elapses.
func waitForTCP(addr string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		conn, err := net.DialTimeout("tcp", addr, time.Second)
		if err == nil {
			_ = conn.Close()
			return nil
		}
		time.Sleep(500 * time.Millisecond)
	}
	return fmt.Errorf("timeout after %s waiting for %s", timeout, addr)
}

// runTunnelgraf launches the binary in the background with the given
// args. Tests should defer stop() to send SIGTERM and wait. Stdout and
// stderr stream to the test logger so failures are diagnosable.
func runTunnelgraf(t *testing.T, ctx context.Context, args ...string) (stop func()) {
	t.Helper()
	cmd := exec.CommandContext(ctx, binaryPath, args...)
	cmd.Dir = repoRoot
	// Run in its own process group so stop() can signal the whole tree
	// (matches the Python suite's preexec_fn=os.setsid pattern).
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Stdout = testWriter{t}
	cmd.Stderr = testWriter{t}
	if err := cmd.Start(); err != nil {
		t.Fatalf("start tunnelgraf: %v", err)
	}
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()

	return func() {
		if cmd.Process == nil {
			return
		}
		_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGTERM)
		select {
		case <-done:
		case <-time.After(10 * time.Second):
			_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
			<-done
		}
	}
}

type testWriter struct{ t *testing.T }

func (w testWriter) Write(p []byte) (int, error) {
	w.t.Logf("%s", p)
	return len(p), nil
}

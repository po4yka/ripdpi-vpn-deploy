package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestRunReadsSecretFromStdinAndReturnsRedactedSuccess(t *testing.T) {
	secret := "ee000000000000000000000000000000006578616d706c652e636f6d"
	request := `{"endpoint":"203.0.113.9","port":10443,"secret":"` + secret + `","timeout_seconds":2}`
	var output bytes.Buffer
	connector := func(_ context.Context, endpoint string, port int, decoded []byte) error {
		if endpoint != "203.0.113.9" || port != 10443 || len(decoded) == 0 {
			t.Fatalf("unexpected connector request: %s %d %d", endpoint, port, len(decoded))
		}
		return nil
	}
	if code := run(strings.NewReader(request), &output, connector); code != 0 {
		t.Fatalf("run code=%d output=%s", code, output.String())
	}
	var response response
	if err := json.Unmarshal(output.Bytes(), &response); err != nil {
		t.Fatal(err)
	}
	if !response.OK || strings.Contains(output.String(), secret) {
		t.Fatalf("unexpected or secret-bearing output: %s", output.String())
	}
}

func TestDecodeSecretAcceptsHexAndURLSafeBase64(t *testing.T) {
	raw := []byte("0123456789abcdef")
	for _, encoded := range []string{"30313233343536373839616263646566", base64.RawURLEncoding.EncodeToString(raw)} {
		decoded, err := decodeSecret(encoded)
		if err != nil || !bytes.Equal(decoded, raw) {
			t.Fatalf("decodeSecret(%q) = %x, %v", encoded, decoded, err)
		}
	}
}

func TestRunTimesOutInjectedConnectorWithoutLeakingError(t *testing.T) {
	secret := "ee00000000000000000000000000000000"
	request := `{"endpoint":"203.0.113.9","port":10443,"secret":"` + secret + `","timeout_seconds":1}`
	var output bytes.Buffer
	connector := func(ctx context.Context, _ string, _ int, _ []byte) error {
		<-ctx.Done()
		return ctx.Err()
	}
	started := time.Now()
	if code := run(strings.NewReader(request), &output, connector); code == 0 {
		t.Fatalf("expected timeout, got %s", output.String())
	}
	if time.Since(started) > 2*time.Second || !strings.Contains(output.String(), "timeout") || strings.Contains(output.String(), secret) {
		t.Fatalf("unexpected timeout response: %s", output.String())
	}
}

func TestRunRedactsInjectedConnectorErrors(t *testing.T) {
	secret := "ee00000000000000000000000000000000"
	request := `{"endpoint":"203.0.113.9","port":10443,"secret":"` + secret + `","timeout_seconds":1}`
	var output bytes.Buffer
	connector := func(context.Context, string, int, []byte) error { return errors.New("sensitive upstream detail") }
	if code := run(strings.NewReader(request), &output, connector); code == 0 {
		t.Fatalf("expected failure, got %s", output.String())
	}
	if strings.Contains(output.String(), secret) || strings.Contains(output.String(), "sensitive upstream detail") {
		t.Fatalf("connector detail leaked: %s", output.String())
	}
}

func TestClassifyConnectorErrorsSeparatesAuthenticationAndTargetAvailability(t *testing.T) {
	if got := classifyConnectError(context.Background(), errors.New("bad proxy secret")); got != "authentication" {
		t.Fatalf("authentication classification = %q", got)
	}
	refused := &net.OpError{Op: "dial", Net: "tcp", Err: syscall.ECONNREFUSED}
	if got := classifyConnectError(context.Background(), refused); got != "target-unavailable" {
		t.Fatalf("target classification = %q", got)
	}
}

func TestRunRejectsMalformedRequestWithoutEchoingInput(t *testing.T) {
	var output bytes.Buffer
	input := `{"secret":"DO_NOT_ECHO"}`
	if code := run(strings.NewReader(input), &output, nil); code == 0 {
		t.Fatalf("expected failure, got %s", output.String())
	}
	if strings.Contains(output.String(), "DO_NOT_ECHO") || !strings.Contains(output.String(), "request-invalid") {
		t.Fatalf("unexpected output: %s", output.String())
	}
}

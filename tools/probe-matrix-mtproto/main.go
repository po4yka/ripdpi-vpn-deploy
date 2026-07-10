package main

import (
	"context"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"strings"
	"syscall"
	"time"

	"github.com/gotd/td/telegram"
	"github.com/gotd/td/telegram/dcs"
)

type request struct {
	Endpoint       string `json:"endpoint"`
	Port           int    `json:"port"`
	Secret         string `json:"secret"`
	TimeoutSeconds int    `json:"timeout_seconds"`
}

type response struct {
	OK        bool   `json:"ok"`
	ErrorKind string `json:"error_kind,omitempty"`
}

type connector func(context.Context, string, int, []byte) error

const helperVersion = "gotd-v0.160.0"

func decodeSecret(value string) ([]byte, error) {
	if decoded, err := hex.DecodeString(value); err == nil {
		return decoded, nil
	}
	if decoded, err := base64.RawURLEncoding.DecodeString(value); err == nil {
		return decoded, nil
	}
	if decoded, err := base64.URLEncoding.DecodeString(value); err == nil {
		return decoded, nil
	}
	return nil, fmt.Errorf("invalid secret encoding")
}

func validate(req request) ([]byte, error) {
	if strings.TrimSpace(req.Endpoint) == "" || req.Port < 1 || req.Port > 65535 || req.TimeoutSeconds < 1 || req.TimeoutSeconds > 60 {
		return nil, fmt.Errorf("invalid request")
	}
	secret, err := decodeSecret(req.Secret)
	if err != nil || len(secret) < 16 {
		return nil, fmt.Errorf("invalid request")
	}
	return secret, nil
}

func realConnect(ctx context.Context, endpoint string, port int, secret []byte) error {
	resolver, err := dcs.MTProxy(net.JoinHostPort(endpoint, fmt.Sprintf("%d", port)), secret, dcs.MTProxyOptions{})
	if err != nil {
		return fmt.Errorf("resolver: %w", err)
	}
	client := telegram.NewClient(telegram.TestAppID, telegram.TestAppHash, telegram.Options{
		Resolver:  resolver,
		NoUpdates: true,
	})
	return client.Run(ctx, func(ctx context.Context) error {
		_, err := client.API().HelpGetNearestDC(ctx)
		if err != nil {
			return fmt.Errorf("nearest dc: %w", err)
		}
		return nil
	})
}

func emit(writer io.Writer, payload response) {
	_ = json.NewEncoder(writer).Encode(payload)
}

func classifyConnectError(ctx context.Context, err error) string {
	if ctx.Err() != nil {
		return "timeout"
	}
	if errors.Is(err, syscall.ECONNREFUSED) || errors.Is(err, syscall.ENETUNREACH) || errors.Is(err, syscall.EHOSTUNREACH) {
		return "target-unavailable"
	}
	var networkError net.Error
	if errors.As(err, &networkError) {
		return "network"
	}
	return "authentication"
}

func run(reader io.Reader, writer io.Writer, connect connector) int {
	limited := io.LimitReader(reader, 1<<20)
	var req request
	if err := json.NewDecoder(limited).Decode(&req); err != nil {
		emit(writer, response{ErrorKind: "request-invalid"})
		return 1
	}
	secret, err := validate(req)
	if err != nil {
		emit(writer, response{ErrorKind: "request-invalid"})
		return 1
	}
	if connect == nil {
		emit(writer, response{ErrorKind: "request-invalid"})
		return 1
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(req.TimeoutSeconds)*time.Second)
	defer cancel()
	if err := connect(ctx, req.Endpoint, req.Port, secret); err != nil {
		emit(writer, response{ErrorKind: classifyConnectError(ctx, err)})
		return 1
	}
	emit(writer, response{OK: true})
	return 0
}

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--version" {
		fmt.Println(helperVersion)
		return
	}
	os.Exit(run(os.Stdin, os.Stdout, realConnect))
}

package vaidcord

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/gorilla/websocket"
)

type GatewayDispatch struct {
	Op   int             `json:"op"`
	Type string          `json:"t"`
	Seq  *int            `json:"s"`
	Data json.RawMessage `json:"d"`
}

type GatewayClient struct {
	client *Client
}

func NewGatewayClient(client *Client) *GatewayClient {
	return &GatewayClient{client: client}
}

func (g *GatewayClient) StreamUpdates(ctx context.Context, intents int) (<-chan GatewayDispatch, <-chan error) {
	updates := make(chan GatewayDispatch)
	errs := make(chan error, 1)
	go func() {
		defer close(updates)
		defer close(errs)
		if err := g.stream(ctx, intents, updates); err != nil && ctx.Err() == nil {
			errs <- err
		}
	}()
	return updates, errs
}

func (g *GatewayClient) stream(ctx context.Context, intents int, updates chan<- GatewayDispatch) error {
	var gatewayInfo struct {
		URL string `json:"url"`
	}
	if err := g.client.DoJSON(ctx, http.MethodGet, "/gateway/bot", nil, &gatewayInfo); err != nil {
		return err
	}
	wsURL, err := buildGatewayURL(gatewayInfo.URL, g.client.config.APIVersion)
	if err != nil {
		return err
	}
	conn, _, err := websocket.DefaultDialer.DialContext(ctx, wsURL, http.Header{
		"User-Agent": []string{UserAgent},
	})
	if err != nil {
		return err
	}
	defer conn.Close()
	conn.SetReadLimit(16 << 20)

	var sequence *int
	var heartbeatTicker *time.Ticker
	defer func() {
		if heartbeatTicker != nil {
			heartbeatTicker.Stop()
		}
	}()

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		_, payload, err := conn.ReadMessage()
		if err != nil {
			return err
		}
		var event GatewayDispatch
		if err := json.Unmarshal(payload, &event); err != nil {
			return err
		}
		if event.Seq != nil {
			sequence = event.Seq
		}

		switch event.Op {
		case 10: // HELLO
			var hello struct {
				HeartbeatInterval float64 `json:"heartbeat_interval"`
			}
			if err := json.Unmarshal(event.Data, &hello); err != nil {
				return err
			}
			if heartbeatTicker != nil {
				heartbeatTicker.Stop()
			}
			heartbeatTicker = time.NewTicker(time.Duration(hello.HeartbeatInterval) * time.Millisecond)
			if err := conn.WriteJSON(map[string]any{
				"op": 2,
				"d": map[string]any{
					"token":   g.client.config.Token,
					"intents": intents,
					"properties": map[string]string{
						"os":      "linux",
						"browser": "vaidcord-go",
						"device":  "vaidcord-go",
					},
				},
			}); err != nil {
				return err
			}
		case 0: // DISPATCH
			select {
			case <-ctx.Done():
				return ctx.Err()
			case updates <- event:
			}
		}

		if heartbeatTicker != nil {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-heartbeatTicker.C:
				if err := conn.WriteJSON(map[string]any{"op": 1, "d": sequence}); err != nil {
					return err
				}
			default:
			}
		}
	}
}

func buildGatewayURL(base string, version string) (string, error) {
	parsed, err := url.Parse(base)
	if err != nil {
		return "", err
	}
	if parsed.Scheme == "" {
		parsed.Scheme = "wss"
	}
	if !strings.HasPrefix(parsed.Scheme, "ws") {
		parsed.Scheme = "wss"
	}
	query := parsed.Query()
	query.Set("v", version)
	query.Set("encoding", "json")
	parsed.RawQuery = query.Encode()
	if parsed.Host == "" {
		return "", fmt.Errorf("invalid gateway URL: %s", base)
	}
	return parsed.String(), nil
}

package vaidcord

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
)

type Client struct {
	config Config
	http   *http.Client
}

func NewClient(config Config, httpClient *http.Client) *Client {
	if httpClient == nil {
		httpClient = http.DefaultClient
	}
	return &Client{config: config.WithDefaults(), http: httpClient}
}

func (c *Client) Endpoint(path string) string {
	path = strings.TrimLeft(path, "/")
	return fmt.Sprintf("%s/v%s/%s", strings.TrimRight(c.config.BaseURL, "/"), c.config.APIVersion, path)
}

func (c *Client) NewRequest(ctx context.Context, method string, path string, body any) (*http.Request, error) {
	if body != nil {
		return nil, fmt.Errorf("vaidcord-go: request bodies are not implemented yet")
	}
	req, err := http.NewRequestWithContext(ctx, method, c.Endpoint(path), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bot "+c.config.Token)
	req.Header.Set("User-Agent", UserAgent)
	req.Header.Set("Accept", "application/json")
	return req, nil
}

func (c *Client) DoJSON(ctx context.Context, method string, path string, out any) error {
	req, err := c.NewRequest(ctx, method, path, nil)
	if err != nil {
		return err
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("vaidcord-go: discord api returned status %d", resp.StatusCode)
	}
	if out == nil || resp.StatusCode == http.StatusNoContent {
		return nil
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

func (c *Client) GetCurrentUser(ctx context.Context) (map[string]any, error) {
	var payload map[string]any
	err := c.DoJSON(ctx, http.MethodGet, "/users/@me", &payload)
	return payload, err
}

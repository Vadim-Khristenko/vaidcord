package vaidcord

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strings"
)

type Client struct {
	config Config
	http   *http.Client
}

func NewClient(config Config, httpClient *http.Client) *Client {
	config = config.WithDefaults()
	if httpClient == nil {
		httpClient = http.DefaultClient
		if config.ProxyURL != "" {
			proxyURL, err := url.Parse(config.ProxyURL)
			if err == nil {
				httpClient = &http.Client{Transport: &http.Transport{Proxy: http.ProxyURL(proxyURL)}}
			}
		}
	}
	return &Client{config: config, http: httpClient}
}

func (c *Client) Endpoint(path string) string {
	path = strings.TrimLeft(path, "/")
	return strings.TrimRight(c.config.BaseURL, "/") + "/v" + c.config.APIVersion + "/" + path
}

func (c *Client) NewRequest(ctx context.Context, method string, path string, body any) (*http.Request, error) {
	var reader io.Reader
	if body != nil {
		payload, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		reader = bytes.NewReader(payload)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.Endpoint(path), reader)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bot "+c.config.Token)
	req.Header.Set("User-Agent", UserAgent)
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	return req, nil
}

func (c *Client) DoJSON(ctx context.Context, method string, path string, body any, out any) error {
	req, err := c.NewRequest(ctx, method, path, body)
	if err != nil {
		return err
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		payload, _ := io.ReadAll(resp.Body)
		apiErr := &APIError{StatusCode: resp.StatusCode, Body: string(payload)}
		var decoded struct {
			Code    int    `json:"code"`
			Message string `json:"message"`
		}
		if json.Unmarshal(payload, &decoded) == nil {
			apiErr.Code = decoded.Code
			apiErr.Message = decoded.Message
		}
		return apiErr
	}
	if out == nil || resp.StatusCode == http.StatusNoContent {
		return nil
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

func (c *Client) GetCurrentUser(ctx context.Context) (User, error) {
	var payload User
	err := c.DoJSON(ctx, http.MethodGet, "/users/@me", nil, &payload)
	return payload, err
}

func (c *Client) FetchChannel(ctx context.Context, channelID string) (Channel, error) {
	var payload Channel
	err := c.DoJSON(ctx, http.MethodGet, "/channels/"+channelID, nil, &payload)
	return payload, err
}

func (c *Client) SendMessage(ctx context.Context, channelID string, message MessagePayload) (Message, error) {
	var payload Message
	err := c.DoJSON(ctx, http.MethodPost, "/channels/"+channelID+"/messages", message, &payload)
	return payload, err
}

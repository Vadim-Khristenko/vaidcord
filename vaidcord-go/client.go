package vaidcord

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// Client is the Discord REST client. It enforces per-route rate-limit
// buckets (X-RateLimit-* headers), sleeps and retries on 429, and retries
// with exponential backoff on 5xx/network failures. All methods accept a
// context and honour its cancellation.
type Client struct {
	config  Config
	http    *http.Client
	limiter *rateLimiter
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
	return &Client{config: config, http: httpClient, limiter: newRateLimiter()}
}

func (c *Client) Endpoint(path string) string {
	path = strings.TrimLeft(path, "/")
	return strings.TrimRight(c.config.BaseURL, "/") + "/v" + c.config.APIVersion + "/" + path
}

func (c *Client) NewRequest(ctx context.Context, method string, path string, body any) (*http.Request, error) {
	var reader io.Reader
	var payload []byte
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		payload = encoded
		reader = bytes.NewReader(payload)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.Endpoint(path), reader)
	if err != nil {
		return nil, err
	}
	c.setHeaders(req, body != nil)
	return req, nil
}

func (c *Client) setHeaders(req *http.Request, hasBody bool) {
	req.Header.Set("Authorization", "Bot "+c.config.Token)
	req.Header.Set("User-Agent", UserAgent)
	req.Header.Set("Accept", "application/json")
	if hasBody {
		req.Header.Set("Content-Type", "application/json")
	}
}

// DoJSON performs a JSON request/response cycle against a Discord route with
// rate limiting and retries. out may be nil for endpoints without a body.
func (c *Client) DoJSON(ctx context.Context, method string, path string, body any, out any) error {
	var payload []byte
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return err
		}
		payload = encoded
	}

	key := routeBucketKey(method, path)
	backoff := 500 * time.Millisecond
	attempts := c.config.MaxRetries + 1
	var lastErr error

	for attempt := 0; attempt < attempts; attempt++ {
		if err := c.limiter.wait(ctx, key); err != nil {
			return err
		}
		var reader io.Reader
		if payload != nil {
			reader = bytes.NewReader(payload)
		}
		req, err := http.NewRequestWithContext(ctx, method, c.Endpoint(path), reader)
		if err != nil {
			return err
		}
		c.setHeaders(req, payload != nil)

		resp, err := c.http.Do(req)
		if err != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			lastErr = err
			if err := sleepContext(ctx, backoff); err != nil {
				return err
			}
			backoff *= 2
			continue
		}
		respBody, readErr := io.ReadAll(resp.Body)
		resp.Body.Close()
		c.limiter.update(key, resp.Header)

		switch {
		case resp.StatusCode == http.StatusTooManyRequests:
			delay := c.limiter.handle429(key, resp.Header, respBody)
			lastErr = decodeAPIError(resp.StatusCode, respBody)
			if err := sleepContext(ctx, delay); err != nil {
				return err
			}
		case resp.StatusCode >= 500:
			lastErr = decodeAPIError(resp.StatusCode, respBody)
			if err := sleepContext(ctx, backoff); err != nil {
				return err
			}
			backoff *= 2
		case resp.StatusCode >= 200 && resp.StatusCode < 300:
			if out == nil || resp.StatusCode == http.StatusNoContent || len(respBody) == 0 {
				return nil
			}
			if readErr != nil {
				return readErr
			}
			return json.Unmarshal(respBody, out)
		default:
			return decodeAPIError(resp.StatusCode, respBody)
		}
	}
	return lastErr
}

func decodeAPIError(statusCode int, body []byte) *APIError {
	apiErr := &APIError{StatusCode: statusCode, Body: string(body)}
	var decoded struct {
		Code    int    `json:"code"`
		Message string `json:"message"`
	}
	if json.Unmarshal(body, &decoded) == nil {
		apiErr.Code = decoded.Code
		apiErr.Message = decoded.Message
	}
	return apiErr
}

// --------------------------------------------------------------------- //
// Users                                                                 //
// --------------------------------------------------------------------- //

func (c *Client) GetCurrentUser(ctx context.Context) (User, error) {
	var payload User
	err := c.DoJSON(ctx, http.MethodGet, "/users/@me", nil, &payload)
	return payload, err
}

// --------------------------------------------------------------------- //
// Channels                                                              //
// --------------------------------------------------------------------- //

func (c *Client) FetchChannel(ctx context.Context, channelID string) (Channel, error) {
	var payload Channel
	err := c.DoJSON(ctx, http.MethodGet, "/channels/"+channelID, nil, &payload)
	return payload, err
}

// ModifyChannel patches channel settings; params holds only the fields to
// change (e.g. {"name": "renamed"}).
func (c *Client) ModifyChannel(ctx context.Context, channelID string, params map[string]any) (Channel, error) {
	var payload Channel
	err := c.DoJSON(ctx, http.MethodPatch, "/channels/"+channelID, params, &payload)
	return payload, err
}

func (c *Client) DeleteChannel(ctx context.Context, channelID string) error {
	return c.DoJSON(ctx, http.MethodDelete, "/channels/"+channelID, nil, nil)
}

// --------------------------------------------------------------------- //
// Messages                                                              //
// --------------------------------------------------------------------- //

func (c *Client) SendMessage(ctx context.Context, channelID string, message MessagePayload) (Message, error) {
	var payload Message
	err := c.DoJSON(ctx, http.MethodPost, "/channels/"+channelID+"/messages", message, &payload)
	return payload, err
}

func (c *Client) GetMessage(ctx context.Context, channelID, messageID string) (Message, error) {
	var payload Message
	err := c.DoJSON(ctx, http.MethodGet, "/channels/"+channelID+"/messages/"+messageID, nil, &payload)
	return payload, err
}

// GetChannelMessages fetches up to limit (max 100) recent messages.
func (c *Client) GetChannelMessages(ctx context.Context, channelID string, limit int) ([]Message, error) {
	path := "/channels/" + channelID + "/messages"
	if limit > 0 {
		path += "?limit=" + strconv.Itoa(limit)
	}
	var payload []Message
	err := c.DoJSON(ctx, http.MethodGet, path, nil, &payload)
	return payload, err
}

func (c *Client) EditMessage(ctx context.Context, channelID, messageID string, message MessagePayload) (Message, error) {
	var payload Message
	err := c.DoJSON(ctx, http.MethodPatch, "/channels/"+channelID+"/messages/"+messageID, message, &payload)
	return payload, err
}

func (c *Client) DeleteMessage(ctx context.Context, channelID, messageID string) error {
	return c.DoJSON(ctx, http.MethodDelete, "/channels/"+channelID+"/messages/"+messageID, nil, nil)
}

// CreateReaction adds the bot's reaction. emoji is either a unicode emoji or
// "name:id" for custom emoji.
func (c *Client) CreateReaction(ctx context.Context, channelID, messageID, emoji string) error {
	return c.DoJSON(ctx, http.MethodPut, reactionPath(channelID, messageID, emoji)+"/@me", nil, nil)
}

func (c *Client) DeleteOwnReaction(ctx context.Context, channelID, messageID, emoji string) error {
	return c.DoJSON(ctx, http.MethodDelete, reactionPath(channelID, messageID, emoji)+"/@me", nil, nil)
}

func (c *Client) DeleteUserReaction(ctx context.Context, channelID, messageID, emoji, userID string) error {
	return c.DoJSON(ctx, http.MethodDelete, reactionPath(channelID, messageID, emoji)+"/"+userID, nil, nil)
}

func (c *Client) DeleteAllReactions(ctx context.Context, channelID, messageID string) error {
	return c.DoJSON(ctx, http.MethodDelete, "/channels/"+channelID+"/messages/"+messageID+"/reactions", nil, nil)
}

func reactionPath(channelID, messageID, emoji string) string {
	return "/channels/" + channelID + "/messages/" + messageID + "/reactions/" + url.PathEscape(emoji)
}

// --------------------------------------------------------------------- //
// Guilds                                                                //
// --------------------------------------------------------------------- //

func (c *Client) FetchGuild(ctx context.Context, guildID string) (Guild, error) {
	var payload Guild
	err := c.DoJSON(ctx, http.MethodGet, "/guilds/"+guildID, nil, &payload)
	return payload, err
}

func (c *Client) GetGuildChannels(ctx context.Context, guildID string) ([]Channel, error) {
	var payload []Channel
	err := c.DoJSON(ctx, http.MethodGet, "/guilds/"+guildID+"/channels", nil, &payload)
	return payload, err
}

func (c *Client) GetGuildRoles(ctx context.Context, guildID string) ([]Role, error) {
	var payload []Role
	err := c.DoJSON(ctx, http.MethodGet, "/guilds/"+guildID+"/roles", nil, &payload)
	return payload, err
}

func (c *Client) GetGuildMember(ctx context.Context, guildID, userID string) (Member, error) {
	var payload Member
	err := c.DoJSON(ctx, http.MethodGet, "/guilds/"+guildID+"/members/"+userID, nil, &payload)
	return payload, err
}

// ListGuildMembers pages through guild members; after is the highest user id
// from the previous page ("" for the first page).
func (c *Client) ListGuildMembers(ctx context.Context, guildID string, limit int, after string) ([]Member, error) {
	query := url.Values{}
	if limit > 0 {
		query.Set("limit", strconv.Itoa(limit))
	}
	if after != "" {
		query.Set("after", after)
	}
	path := "/guilds/" + guildID + "/members"
	if encoded := query.Encode(); encoded != "" {
		path += "?" + encoded
	}
	var payload []Member
	err := c.DoJSON(ctx, http.MethodGet, path, nil, &payload)
	return payload, err
}

// --------------------------------------------------------------------- //
// Interactions                                                          //
// --------------------------------------------------------------------- //

// CreateInteractionResponse answers an interaction within its 3s window.
func (c *Client) CreateInteractionResponse(ctx context.Context, interactionID, token string, response InteractionResponse) error {
	return c.DoJSON(ctx, http.MethodPost, "/interactions/"+interactionID+"/"+token+"/callback", response, nil)
}

func (c *Client) CreateFollowupMessage(ctx context.Context, applicationID, token string, message MessagePayload) (Message, error) {
	var payload Message
	err := c.DoJSON(ctx, http.MethodPost, "/webhooks/"+applicationID+"/"+token, message, &payload)
	return payload, err
}

func (c *Client) EditOriginalInteractionResponse(ctx context.Context, applicationID, token string, message MessagePayload) (Message, error) {
	var payload Message
	err := c.DoJSON(ctx, http.MethodPatch, "/webhooks/"+applicationID+"/"+token+"/messages/@original", message, &payload)
	return payload, err
}

func (c *Client) DeleteOriginalInteractionResponse(ctx context.Context, applicationID, token string) error {
	return c.DoJSON(ctx, http.MethodDelete, "/webhooks/"+applicationID+"/"+token+"/messages/@original", nil, nil)
}

// --------------------------------------------------------------------- //
// Webhooks                                                              //
// --------------------------------------------------------------------- //

// ExecuteWebhook posts through a webhook. With wait=true Discord returns the
// created message; otherwise the returned Message is zero.
func (c *Client) ExecuteWebhook(ctx context.Context, webhookID, token string, message MessagePayload, wait bool) (Message, error) {
	path := "/webhooks/" + webhookID + "/" + token
	var payload Message
	if wait {
		err := c.DoJSON(ctx, http.MethodPost, path+"?wait=true", message, &payload)
		return payload, err
	}
	err := c.DoJSON(ctx, http.MethodPost, path, message, nil)
	return payload, err
}

// --------------------------------------------------------------------- //
// Threads                                                               //
// --------------------------------------------------------------------- //

type ThreadPayload struct {
	Name                string `json:"name"`
	AutoArchiveDuration int    `json:"auto_archive_duration,omitempty"`
	Type                int    `json:"type,omitempty"`
	Invitable           *bool  `json:"invitable,omitempty"`
	RateLimitPerUser    int    `json:"rate_limit_per_user,omitempty"`
}

func (c *Client) StartThreadWithMessage(ctx context.Context, channelID, messageID string, thread ThreadPayload) (Channel, error) {
	var payload Channel
	err := c.DoJSON(ctx, http.MethodPost, "/channels/"+channelID+"/messages/"+messageID+"/threads", thread, &payload)
	return payload, err
}

func (c *Client) StartThreadWithoutMessage(ctx context.Context, channelID string, thread ThreadPayload) (Channel, error) {
	var payload Channel
	err := c.DoJSON(ctx, http.MethodPost, "/channels/"+channelID+"/threads", thread, &payload)
	return payload, err
}

func (c *Client) JoinThread(ctx context.Context, channelID string) error {
	return c.DoJSON(ctx, http.MethodPut, "/channels/"+channelID+"/thread-members/@me", nil, nil)
}

func (c *Client) LeaveThread(ctx context.Context, channelID string) error {
	return c.DoJSON(ctx, http.MethodDelete, "/channels/"+channelID+"/thread-members/@me", nil, nil)
}

// --------------------------------------------------------------------- //
// Application commands                                                  //
// --------------------------------------------------------------------- //

func (c *Client) ListGlobalCommands(ctx context.Context, applicationID string) ([]map[string]any, error) {
	var payload []map[string]any
	err := c.DoJSON(ctx, http.MethodGet, "/applications/"+applicationID+"/commands", nil, &payload)
	return payload, err
}

func (c *Client) BulkOverwriteGlobalCommands(
	ctx context.Context,
	applicationID string,
	commands []map[string]any,
) ([]map[string]any, error) {
	var payload []map[string]any
	err := c.DoJSON(ctx, http.MethodPut, "/applications/"+applicationID+"/commands", commands, &payload)
	return payload, err
}

func (c *Client) ListGuildCommands(ctx context.Context, applicationID string, guildID string) ([]map[string]any, error) {
	var payload []map[string]any
	err := c.DoJSON(ctx, http.MethodGet, "/applications/"+applicationID+"/guilds/"+guildID+"/commands", nil, &payload)
	return payload, err
}

func (c *Client) BulkOverwriteGuildCommands(
	ctx context.Context,
	applicationID string,
	guildID string,
	commands []map[string]any,
) ([]map[string]any, error) {
	var payload []map[string]any
	err := c.DoJSON(ctx, http.MethodPut, "/applications/"+applicationID+"/guilds/"+guildID+"/commands", commands, &payload)
	return payload, err
}

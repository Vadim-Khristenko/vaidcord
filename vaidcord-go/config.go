package vaidcord

type Config struct {
	Token      string
	APIVersion string
	BaseURL    string
	ProxyURL   string
	// MaxRetries bounds retries after 429/5xx/network failures (default 3).
	MaxRetries int
}

func (c Config) WithDefaults() Config {
	if c.APIVersion == "" {
		c.APIVersion = "10"
	}
	if c.BaseURL == "" {
		c.BaseURL = "https://discord.com/api"
	}
	if c.MaxRetries <= 0 {
		c.MaxRetries = 3
	}
	return c
}

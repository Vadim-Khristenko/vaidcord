package vaidcord

type Config struct {
	Token      string
	APIVersion string
	BaseURL    string
	ProxyURL   string
}

func (c Config) WithDefaults() Config {
	if c.APIVersion == "" {
		c.APIVersion = "10"
	}
	if c.BaseURL == "" {
		c.BaseURL = "https://discord.com/api"
	}
	return c
}

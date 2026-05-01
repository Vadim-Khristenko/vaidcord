package vaidcord

const (
	LibraryName = "vaidcord-go"
	Version     = "0.1.0"
)

type Config struct {
	Token      string
	APIVersion string
	BaseURL    string
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

package vaidcord

import "fmt"

type APIError struct {
	StatusCode int
	Code       int
	Message    string
	Body       string
}

func (e *APIError) Error() string {
	if e.Code != 0 || e.Message != "" {
		return fmt.Sprintf("vaidcord-go: discord api returned status %d code %d: %s", e.StatusCode, e.Code, e.Message)
	}
	return fmt.Sprintf("vaidcord-go: discord api returned status %d: %s", e.StatusCode, e.Body)
}

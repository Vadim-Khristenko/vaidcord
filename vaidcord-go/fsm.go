package vaidcord

import (
	"context"
	"fmt"
	"sync"
)

// FSMScope selects which conversation dimension a state key binds to,
// mirroring the Python fsm package's StorageKey scopes.
type FSMScope string

const (
	FSMScopeUser    FSMScope = "user"
	FSMScopeChannel FSMScope = "channel"
	FSMScopeGuild   FSMScope = "guild"
	FSMScopeMember  FSMScope = "member"
	FSMScopeCustom  FSMScope = "custom"
)

// FSMKey addresses one finite-state-machine slot.
type FSMKey struct {
	Scope     FSMScope
	GuildID   string
	ChannelID string
	UserID    string
	Custom    string
}

func (k FSMKey) String() string {
	return fmt.Sprintf("%s:%s:%s:%s:%s", k.Scope, k.GuildID, k.ChannelID, k.UserID, k.Custom)
}

// FSMStorage persists states and per-key data bags.
type FSMStorage interface {
	GetState(ctx context.Context, key FSMKey) (string, error)
	SetState(ctx context.Context, key FSMKey, state string) error
	GetData(ctx context.Context, key FSMKey) (map[string]any, error)
	SetData(ctx context.Context, key FSMKey, data map[string]any) error
	UpdateData(ctx context.Context, key FSMKey, values map[string]any) (map[string]any, error)
	Clear(ctx context.Context, key FSMKey) error
}

// MemoryFSMStorage is the in-memory FSMStorage; safe for concurrent use.
type MemoryFSMStorage struct {
	mu     sync.Mutex
	states map[string]string
	data   map[string]map[string]any
}

func NewMemoryFSMStorage() *MemoryFSMStorage {
	return &MemoryFSMStorage{
		states: make(map[string]string),
		data:   make(map[string]map[string]any),
	}
}

func (s *MemoryFSMStorage) GetState(_ context.Context, key FSMKey) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.states[key.String()], nil
}

func (s *MemoryFSMStorage) SetState(_ context.Context, key FSMKey, state string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if state == "" {
		delete(s.states, key.String())
	} else {
		s.states[key.String()] = state
	}
	return nil
}

func (s *MemoryFSMStorage) GetData(_ context.Context, key FSMKey) (map[string]any, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return copyFSMData(s.data[key.String()]), nil
}

func (s *MemoryFSMStorage) SetData(_ context.Context, key FSMKey, data map[string]any) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(data) == 0 {
		delete(s.data, key.String())
	} else {
		s.data[key.String()] = copyFSMData(data)
	}
	return nil
}

func (s *MemoryFSMStorage) UpdateData(_ context.Context, key FSMKey, values map[string]any) (map[string]any, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	current := s.data[key.String()]
	if current == nil {
		current = make(map[string]any, len(values))
		s.data[key.String()] = current
	}
	for name, value := range values {
		current[name] = value
	}
	return copyFSMData(current), nil
}

func (s *MemoryFSMStorage) Clear(_ context.Context, key FSMKey) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.states, key.String())
	delete(s.data, key.String())
	return nil
}

func copyFSMData(data map[string]any) map[string]any {
	out := make(map[string]any, len(data))
	for name, value := range data {
		out[name] = value
	}
	return out
}

// FSMContext is a convenience wrapper binding a storage to one key.
type FSMContext struct {
	Storage FSMStorage
	Key     FSMKey
}

func (c FSMContext) GetState(ctx context.Context) (string, error) {
	return c.Storage.GetState(ctx, c.Key)
}

func (c FSMContext) SetState(ctx context.Context, state string) error {
	return c.Storage.SetState(ctx, c.Key, state)
}

func (c FSMContext) GetData(ctx context.Context) (map[string]any, error) {
	return c.Storage.GetData(ctx, c.Key)
}

func (c FSMContext) SetData(ctx context.Context, data map[string]any) error {
	return c.Storage.SetData(ctx, c.Key, data)
}

func (c FSMContext) UpdateData(ctx context.Context, values map[string]any) (map[string]any, error) {
	return c.Storage.UpdateData(ctx, c.Key, values)
}

func (c FSMContext) Clear(ctx context.Context) error {
	return c.Storage.Clear(ctx, c.Key)
}

// FSMManager mints FSMContexts for the common scopes.
type FSMManager struct {
	Storage FSMStorage
}

func NewFSMManager(storage FSMStorage) *FSMManager {
	if storage == nil {
		storage = NewMemoryFSMStorage()
	}
	return &FSMManager{Storage: storage}
}

func (m *FSMManager) User(userID string) FSMContext {
	return FSMContext{Storage: m.Storage, Key: FSMKey{Scope: FSMScopeUser, UserID: userID}}
}

func (m *FSMManager) Channel(channelID string) FSMContext {
	return FSMContext{Storage: m.Storage, Key: FSMKey{Scope: FSMScopeChannel, ChannelID: channelID}}
}

func (m *FSMManager) Guild(guildID string) FSMContext {
	return FSMContext{Storage: m.Storage, Key: FSMKey{Scope: FSMScopeGuild, GuildID: guildID}}
}

func (m *FSMManager) Member(guildID, userID string) FSMContext {
	return FSMContext{Storage: m.Storage, Key: FSMKey{Scope: FSMScopeMember, GuildID: guildID, UserID: userID}}
}

func (m *FSMManager) Custom(customID string) FSMContext {
	return FSMContext{Storage: m.Storage, Key: FSMKey{Scope: FSMScopeCustom, Custom: customID}}
}

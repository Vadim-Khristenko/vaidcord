package admin

import (
	"context"
	"fmt"

	"github.com/Vadim-Khristenko/vaidcord/vaidcord-go"
)

type Deps struct {
	OwnerID string
}

func Router(deps Deps) *vaidcord.Router {
	router := vaidcord.NewRouter("admin")
	router.OnMessageCreate(vaidcord.AuthorID(deps.OwnerID), vaidcord.ContentStartsWith("!admin")).Handle(
		func(_ context.Context, message vaidcord.Message) error {
			fmt.Println("admin command", message.Content)
			return nil
		},
	)
	return router
}

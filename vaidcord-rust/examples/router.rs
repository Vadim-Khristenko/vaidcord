fn main() -> Result<(), vaidcord::Error> {
    let mut router = vaidcord::Router::new();

    vaidcord::register_on_message!(
        router,
        |message: &vaidcord::Message| {
            println!("{}", vaidcord::inline_code(&message.content));
            Ok(())
        },
        filters = [vaidcord::command("start")]
    );

    let message = vaidcord::Message {
        id: "1".to_string(),
        channel_id: "2".to_string(),
        guild_id: None,
        author: vaidcord::User {
            id: "42".to_string(),
            username: "tester".to_string(),
            discriminator: None,
            global_name: None,
            bot: false,
            system: false,
            avatar: None,
            banner: None,
            public_flags: None,
        },
        content: "/start".to_string(),
        timestamp: None,
        edited_timestamp: None,
        tts: false,
        mention_everyone: false,
        mentions: Vec::new(),
        embeds: Vec::new(),
        attachments: Vec::new(),
        components: Vec::new(),
        flags: None,
    };

    router.dispatch_message(&message)
}

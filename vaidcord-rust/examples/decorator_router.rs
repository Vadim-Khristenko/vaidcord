use vaidcord::{HandlerResult, Message, Router, command};

#[vaidcord::on_message(filter = command!("age"))]
fn age(message: &Message) -> HandlerResult {
    println!("{} sent {}", message.author.username, message.content);
    Ok(())
}

fn main() -> Result<(), vaidcord::Error> {
    let mut router = Router::new();
    router.add_message_handler(age_message_handler());

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
        content: "/age".to_string(),
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

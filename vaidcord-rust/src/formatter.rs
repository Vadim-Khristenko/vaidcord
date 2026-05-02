pub fn escape_markdown(text: &str) -> String {
    let mut escaped = String::with_capacity(text.len());
    for char in text.chars() {
        match char {
            '\\' | '*' | '_' | '`' | '~' | '|' | '>' => {
                escaped.push('\\');
                escaped.push(char);
            }
            _ => escaped.push(char),
        }
    }
    escaped
}

pub fn bold(text: impl AsRef<str>) -> String {
    format!("**{}**", text.as_ref())
}

pub fn italic(text: impl AsRef<str>) -> String {
    format!("*{}*", text.as_ref())
}

pub fn inline_code(text: impl AsRef<str>) -> String {
    format!("`{}`", text.as_ref().replace('`', "\\`"))
}

pub fn code_block(code: impl AsRef<str>, language: impl AsRef<str>) -> String {
    let escaped = code.as_ref().replace("```", "\\`\\`\\`");
    let language = language.as_ref();
    if language.is_empty() {
        format!("```\n{escaped}\n```")
    } else {
        format!("```{language}\n{escaped}\n```")
    }
}

pub fn mention_user(user_id: impl AsRef<str>) -> String {
    format!("<@{}>", user_id.as_ref())
}

pub fn mention_channel(channel_id: impl AsRef<str>) -> String {
    format!("<#{}>", channel_id.as_ref())
}

pub fn mention_role(role_id: impl AsRef<str>) -> String {
    format!("<@&{}>", role_id.as_ref())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn formats_discord_markdown() {
        assert_eq!(bold("ok"), "**ok**");
        assert_eq!(mention_channel("123"), "<#123>");
        assert_eq!(escape_markdown("*hi*"), "\\*hi\\*");
    }
}

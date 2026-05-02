fn main() {
    let client = vaidcord::Client::new(vaidcord::Config::new("BOT_TOKEN"));
    let request = client.request_parts("GET", "/users/@me", false);

    println!("{}", request.url);
    println!("{}", vaidcord::bold("ready"));
}

use anyhow::Result;
use askama::Template;

#[derive(Debug, Clone)]
pub struct Link {
    pub label: String,
    pub url: String,
}

impl From<(&str, &str)> for Link {
    fn from((label, url): (&str, &str)) -> Self {
        Self {
            label: label.into(),
            url: url.into(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct AppCard {
    pub platform: String,
    pub primary: Link,
    pub also: Vec<Link>,
}

pub struct RecipientCtx<'a> {
    pub client_name: &'a str,
    pub host: &'a str,
    pub env: &'a str,
    pub provider: &'a str,
    pub subscription_url: &'a str,
    pub singbox_deeplink: &'a str,
    pub ripdpi_deeplink: &'a str,
    pub apps: Vec<AppCard>,
}

#[derive(Template)]
#[template(path = "recipient.html", escape = "html")]
struct RecipientTemplate<'a> {
    client_name: &'a str,
    host: &'a str,
    env: &'a str,
    provider: &'a str,
    subscription_url: &'a str,
    singbox_deeplink: &'a str,
    ripdpi_deeplink: &'a str,
    apps: &'a [AppCard],
}

pub fn render(ctx: &RecipientCtx<'_>) -> Result<String> {
    let t = RecipientTemplate {
        client_name: ctx.client_name,
        host: ctx.host,
        env: ctx.env,
        provider: ctx.provider,
        subscription_url: ctx.subscription_url,
        singbox_deeplink: ctx.singbox_deeplink,
        ripdpi_deeplink: ctx.ripdpi_deeplink,
        apps: &ctx.apps,
    };
    Ok(t.render()?)
}

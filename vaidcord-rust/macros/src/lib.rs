//! Procedural macros for the VaidCord Rust SDK.
//!
//! The headline macro is `#[on_message]`. It accepts:
//!
//! * No arguments — handler runs for every message:
//!   `#[on_message]`
//! * A single positional filter (legacy single-filter form):
//!   `#[on_message(content_starts_with("!"))]`
//! * Multiple positional filters — combined with logical AND (the new
//!   mainstream pattern):
//!   `#[on_message(content_starts_with("!"), command!("ping"))]`
//! * `filter = expr` — back-compat single-filter named form:
//!   `#[on_message(filter = command!("ping"))]`
//! * `filters = [expr, expr, ...]` — explicit multi-filter named form:
//!   `#[on_message(filters = [content_starts_with("!"), command!("ping")])]`
//! * `any = [expr, expr, ...]` — OR composition: at least one filter must pass:
//!   `#[on_message(any = [command!("ping"), command!("pong")])]`
//!
//! The forms can be combined: `filters = [...]` AND `any = [...]` both apply.

use proc_macro::TokenStream;
use quote::{format_ident, quote};
use syn::{
    Expr, Ident, ItemFn, Token,
    parse::{Parse, ParseStream},
    parse_macro_input,
    punctuated::Punctuated,
    token::Bracket,
};

#[derive(Default)]
struct OnMessageArgs {
    filters: Vec<Expr>,
    any_of: Vec<Expr>,
}

impl Parse for OnMessageArgs {
    fn parse(input: ParseStream<'_>) -> syn::Result<Self> {
        let mut out = Self::default();
        if input.is_empty() {
            return Ok(out);
        }

        // Parse a single named or positional argument at a time.
        loop {
            if input.peek(Ident) && input.peek2(Token![=]) {
                let key: Ident = input.parse()?;
                input.parse::<Token![=]>()?;
                let key_str = key.to_string();
                match key_str.as_str() {
                    "filter" => {
                        out.filters.push(input.parse()?);
                    }
                    "filters" => {
                        out.filters.extend(parse_bracketed_exprs(input)?);
                    }
                    "any" | "any_of" => {
                        out.any_of.extend(parse_bracketed_exprs(input)?);
                    }
                    other => {
                        return Err(syn::Error::new_spanned(
                            key,
                            format!(
                                "expected `filter = ...`, `filters = [..]`, or `any = [..]`; got `{other}`"
                            ),
                        ));
                    }
                }
            } else {
                out.filters.push(input.parse()?);
            }

            if input.peek(Token![,]) {
                input.parse::<Token![,]>()?;
                if input.is_empty() {
                    break;
                }
                continue;
            }
            break;
        }
        Ok(out)
    }
}

fn parse_bracketed_exprs(input: ParseStream<'_>) -> syn::Result<Vec<Expr>> {
    if !input.peek(Bracket) {
        return Err(input.error("expected `[ expr, expr, ... ]`"));
    }
    let content;
    syn::bracketed!(content in input);
    let parsed = Punctuated::<Expr, Token![,]>::parse_terminated(&content)?;
    Ok(parsed.into_iter().collect())
}

#[proc_macro_attribute]
pub fn on_message(args: TokenStream, input: TokenStream) -> TokenStream {
    let input_fn = parse_macro_input!(input as ItemFn);
    let args = parse_macro_input!(args as OnMessageArgs);
    let fn_name = &input_fn.sig.ident;
    let registration_name = format_ident!("{fn_name}_message_handler");

    let mut filter_exprs: Vec<proc_macro2::TokenStream> =
        args.filters.into_iter().map(|f| quote! { #f }).collect();

    if !args.any_of.is_empty() {
        let any_exprs = args.any_of;
        // Compose with `or` from vaidcord::filters; reduce N filters into a
        // single OR-chained MessageFilter so the router still treats the
        // group as one entry in its filters Vec.
        let or_chain = quote! {
            {
                let mut __any: Vec<::vaidcord::MessageFilter> = vec![#( #any_exprs ),*];
                let mut __iter = __any.drain(..);
                let mut __acc = __iter
                    .next()
                    .expect("`any = [..]` must contain at least one filter");
                for __f in __iter {
                    __acc = ::vaidcord::or(__acc, __f);
                }
                __acc
            }
        };
        filter_exprs.push(or_chain);
    }

    let filter_tokens = if filter_exprs.is_empty() {
        quote! { Vec::new() }
    } else {
        quote! { vec![#( #filter_exprs ),*] }
    };

    quote! {
        #input_fn

        pub fn #registration_name() -> ::vaidcord::MessageHandlerDef {
            ::vaidcord::MessageHandlerDef::new(
                stringify!(#fn_name),
                #fn_name,
                #filter_tokens,
            )
        }
    }
    .into()
}

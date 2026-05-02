use proc_macro::TokenStream;
use quote::{format_ident, quote};
use syn::{Expr, Ident, ItemFn, Token, parse::Parse, parse::ParseStream, parse_macro_input};

struct OnMessageArgs {
    filter: Option<Expr>,
}

impl Parse for OnMessageArgs {
    fn parse(input: ParseStream<'_>) -> syn::Result<Self> {
        if input.is_empty() {
            return Ok(Self { filter: None });
        }
        if input.peek(Ident) && input.peek2(Token![=]) {
            let ident: Ident = input.parse()?;
            if ident != "filter" {
                return Err(syn::Error::new_spanned(ident, "expected `filter = ...`"));
            }
            input.parse::<Token![=]>()?;
            return Ok(Self {
                filter: Some(input.parse()?),
            });
        }
        Ok(Self {
            filter: Some(input.parse()?),
        })
    }
}

#[proc_macro_attribute]
pub fn on_message(args: TokenStream, input: TokenStream) -> TokenStream {
    let input_fn = parse_macro_input!(input as ItemFn);
    let args = parse_macro_input!(args as OnMessageArgs);
    let fn_name = &input_fn.sig.ident;
    let registration_name = format_ident!("{fn_name}_message_handler");

    let filter_tokens = match args.filter {
        Some(filter) => quote! { vec![#filter] },
        None => quote! { Vec::new() },
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

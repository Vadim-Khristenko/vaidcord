use proc_macro::TokenStream;
use quote::{format_ident, quote};
use syn::{ItemFn, parse_macro_input};

#[proc_macro_attribute]
pub fn on_message(args: TokenStream, input: TokenStream) -> TokenStream {
    let input_fn = parse_macro_input!(input as ItemFn);
    let filters = proc_macro2::TokenStream::from(args);
    let fn_name = &input_fn.sig.ident;
    let registration_name = format_ident!("{fn_name}_message_handler");

    let filter_tokens = if filters.is_empty() {
        quote! { Vec::new() }
    } else {
        quote! { vec![#filters] }
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

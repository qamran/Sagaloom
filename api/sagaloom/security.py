def wrap_untrusted(text: str, source: str) -> str:
    safe = text.replace("</untrusted_data", "&lt;/untrusted_data")
    return f'<untrusted_data source="{source}">\n{safe}\n</untrusted_data>'

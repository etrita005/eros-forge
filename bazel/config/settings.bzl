"""Small dependency-free string build setting."""

ForgeBuildSettingInfo = provider(fields = {"value": "Validated string value."})

def _string_flag_impl(ctx):
    value = ctx.build_setting_value
    if value not in ctx.attr.values:
        fail("%s: unsupported value %r; allowed: %s. MSan is not supported by Forge's GCC toolchains." % (ctx.label, value, ", ".join(ctx.attr.values)))
    return [ForgeBuildSettingInfo(value = value)]

string_flag = rule(
    implementation = _string_flag_impl,
    build_setting = config.string(flag = True),
    attrs = {"values": attr.string_list(mandatory = True)},
)

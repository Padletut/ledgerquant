"""Conservative reservation, including unknown dispatches; no usage refunds."""

from decimal import Decimal, ROUND_CEILING

from ledgerquant.research.types import canonical


def micro_usd(amount):
    return int((Decimal(str(amount)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


def reservation(profile, request):
    # UTF-8 byte count exceeds text token count. Reserve additional framing space
    # for provider-side function formatting. The actual provider bill remains
    # authoritative; rate changes require a new profile and reservation policy.
    incoming = len(canonical(request).encode()) + 4096
    outgoing = profile.max_output_tokens
    price = Decimal(str(max(profile.input_usd_per_million, profile.cache_write_usd_per_million))) * incoming
    price += Decimal(str(profile.output_usd_per_million)) * outgoing
    return incoming + outgoing, int(price.to_integral_value(rounding=ROUND_CEILING))

"""attestor.gateway — Pillar I: trade ingestion and normalisation."""

from attestor.gateway.parser import (
    order_to_dict as order_to_dict,
)
from attestor.gateway.parser import (
    parse_order as parse_order,
)
from attestor.gateway.types import (
    CanonicalOrder as CanonicalOrder,
)
from attestor.gateway.types import (
    OrderSide as OrderSide,
)
from attestor.gateway.types import (
    OrderType as OrderType,
)

"""Unit checks on the catalog ORM models (no database required)."""

from app.db.models import EMBEDDING_DIM, Base, Brand, Partner, Product


def test_expected_tables_are_registered() -> None:
    tables = set(Base.metadata.tables)
    assert {"partners", "brands", "products"} <= tables


def test_product_has_search_and_vector_fields() -> None:
    columns = {c.name for c in Product.__table__.columns}
    # Shared columns that drive cross-partner search + ranking.
    assert {"partner_id", "name", "price_cents", "currency", "attrs", "embedding"} <= columns


def test_embedding_dimension_is_consistent() -> None:
    # The model's vector size must match the configured embedding dimensionality.
    embedding = Product.__table__.columns["embedding"]
    assert embedding.type.dim == EMBEDDING_DIM  # type: ignore[attr-defined]


def test_relationships_link_partner_brand_product() -> None:
    assert Partner.products.property.mapper.class_ is Product
    assert Brand.products.property.mapper.class_ is Product
    assert Product.partner.property.mapper.class_ is Partner

"""Pick the data source from configuration and compare dataset identities."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Discriminator, Tag, TypeAdapter

from src.data.ecb import EcbCsvConfig, EcbSource, ecb_identity
from src.data.synthetic import SyntheticConfig, SyntheticSource, dataset_id


def _source_tag(value: Any) -> str:
    # configs stored before `source` existed are synthetic
    if isinstance(value, dict):
        return value.get("source", "synthetic")
    return getattr(value, "source", "synthetic")


DataConfig = Annotated[
    Annotated[SyntheticConfig, Tag("synthetic")]
    | Annotated[EcbCsvConfig, Tag("ecb_csv")],
    Discriminator(_source_tag),
]
_adapter: TypeAdapter[SyntheticConfig | EcbCsvConfig] = TypeAdapter(DataConfig)


def parse_data_config(data: dict[str, Any]) -> SyntheticConfig | EcbCsvConfig:
    return _adapter.validate_python(data)


def dataset_identity(cfg: SyntheticConfig | EcbCsvConfig) -> str:
    """Id of the generated/loaded dataset (includes the CSV content for ECB)."""
    if isinstance(cfg, EcbCsvConfig):
        return ecb_identity(cfg)
    return dataset_id(cfg)


def same_dataset(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True if two stored data configurations describe the same dataset."""
    return dataset_identity(parse_data_config(a)) == dataset_identity(
        parse_data_config(b)
    )


def load_source(cfg: SyntheticConfig | EcbCsvConfig) -> SyntheticSource | EcbSource:
    if isinstance(cfg, EcbCsvConfig):
        return EcbSource(cfg)
    return SyntheticSource(cfg)

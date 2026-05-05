from .fixed_size import FixedSizeChunker
from .hierarchical import HierarchicalChunker


def create_chunker(strategy: str, **kwargs) -> FixedSizeChunker | HierarchicalChunker:
    key = strategy.strip().lower()

    if key == "fixed_size":
        return FixedSizeChunker(**kwargs)

    if key == "hierarchical":
        return HierarchicalChunker(**kwargs)

    raise ValueError(
        "Unsupported chunking strategy. Use 'fixed_size' or 'hierarchical'."
    )
"""The common 27-lane source registry foundation.

A registry over the frozen source configs — not any single lane's adapter.
"""

from .config import load_source_configs


class SourceRegistry:
    """All 27 approved lanes: lane_id, source_id, acquisition, roles, policies."""

    def __init__(self, configs):
        self._by_lane = {config.lane: config for config in configs}
        self._by_slug = {config.source_id: config for config in configs}

    @classmethod
    def load(cls, root):
        return cls(load_source_configs(root))

    @property
    def configs(self):
        return tuple(self._by_lane[lane] for lane in sorted(self._by_lane))

    def __len__(self):
        return len(self._by_lane)

    def by_lane_id(self, lane_id):
        if not isinstance(lane_id, str) or not lane_id.startswith("S"):
            raise KeyError(f"lane_id must be an S01-S27 identifier, got {lane_id!r}")
        try:
            lane = int(lane_id[1:])
        except ValueError as exc:
            raise KeyError(f"lane_id must be an S01-S27 identifier, got {lane_id!r}") from exc
        try:
            return self._by_lane[lane]
        except KeyError as exc:
            raise KeyError(f"unknown lane: {lane_id}") from exc

    def by_source_id(self, slug):
        try:
            return self._by_slug[slug]
        except KeyError as exc:
            raise KeyError(f"unknown source_id: {slug}") from exc

    def describe(self, config):
        """The registry view of one lane: identity, acquisition and policies."""
        return {
            "lane_id": config.lane_id,
            "source_id": config.source_id,
            "acquisition_mode": config.acquisition,
            "source_role": config.role,
            "kmx_capability": tuple(config.kmx_levels),
            "evidence_role": config.evidence,
            "rule_policy": config.rules,
            "jurisdiction": config.jurisdiction,
            "object_storage_prefix": config.object_storage_prefix,
            "rate_limit_policy": config.rate_limit,
        }


def load_source_registry(root):
    """Load the common registry for all 27 approved lanes."""
    return SourceRegistry.load(root)

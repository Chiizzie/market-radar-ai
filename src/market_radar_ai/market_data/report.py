from dataclasses import dataclass, field

@dataclass
class ScanReport:
    discovered: int = 0
    fetched: int = 0
    quality_passed: int = 0
    shortlisted: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    provider_errors: dict[str, int] = field(default_factory=dict)
    def reject(self, reason: str, count: int = 1) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + count
    def provider_error(self, provider: str, count: int = 1) -> None:
        self.provider_errors[provider] = self.provider_errors.get(provider, 0) + count
    def as_dict(self) -> dict:
        return {"discovered": self.discovered, "fetched": self.fetched,
            "quality_passed": self.quality_passed, "shortlisted": self.shortlisted,
            "rejected": dict(sorted(self.rejected.items())), "provider_errors": dict(sorted(self.provider_errors.items()))}

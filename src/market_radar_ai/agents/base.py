from abc import ABC, abstractmethod
from market_radar_ai.schemas import CandidateSnapshot, AgentReport

class SpecialistAgent(ABC):
    agent_id: str
    prompt_version: str = "v1"

    @abstractmethod
    def analyse_independently(self, candidate: CandidateSnapshot) -> AgentReport:
        """Analyse only the immutable candidate snapshot; no peer reports available."""
        raise NotImplementedError

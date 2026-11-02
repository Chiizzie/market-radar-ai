from dataclasses import dataclass
from market_radar_ai.schemas import CandidateSnapshot, AgentReport, FinalDecision

@dataclass
class AnalysisBundle:
    candidate: CandidateSnapshot
    independent_reports: list[AgentReport]
    debate_records: list[dict]
    decision: FinalDecision | None = None

class AnalysisPipeline:
    """Orchestration boundary. Provider and agent implementations are injected later."""

    def __init__(self, agents: list, debate_engine, decision_agent):
        self.agents = agents
        self.debate_engine = debate_engine
        self.decision_agent = decision_agent

    def run(self, candidate: CandidateSnapshot) -> AnalysisBundle:
        if not candidate.data_quality_passed:
            raise ValueError("Candidate failed data quality; it must not enter agent analysis.")
        reports = [agent.analyse_independently(candidate) for agent in self.agents]
        # Debate is deliberately invoked only after every independent report exists.
        debate = self.debate_engine.run(candidate, reports)
        decision = self.decision_agent.decide(candidate, reports, debate)
        return AnalysisBundle(candidate, reports, debate, decision)

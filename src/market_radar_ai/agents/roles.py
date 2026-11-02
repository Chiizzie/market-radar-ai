from enum import StrEnum

class AgentRole(StrEnum):
    OPPORTUNITY_HUNTER = "opportunity_hunter"
    TECHNICAL_ANALYST = "technical_analyst"
    NEWS_ANALYST = "news_analyst"
    DEVILS_ADVOCATE = "devils_advocate"
    RISK_MANAGER = "risk_manager"
    FINAL_DECISION = "final_decision"

INDEPENDENT_FIRST_PASS = {
    AgentRole.OPPORTUNITY_HUNTER,
    AgentRole.TECHNICAL_ANALYST,
    AgentRole.NEWS_ANALYST,
    AgentRole.DEVILS_ADVOCATE,
    AgentRole.RISK_MANAGER,
}

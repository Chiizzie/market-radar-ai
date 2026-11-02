"""Offline model contract. Only mock transport is enabled until paid activation review."""
from dataclasses import dataclass
from datetime import datetime
import json
from .paper_team import RoleReport
from .prompts import instruction, VERSION


@dataclass(frozen=True)
class ModelReply:
    text: str
    cost_microeur: int = 0


class MockTransport:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    def complete(self, request, *, timeout_seconds):
        self.requests.append(request)
        reply = next(self.replies)
        if isinstance(reply, Exception): raise reply
        return reply


class ModelGateway:
    """Reserves before transport; malformed replies fail closed after usage settlement.

    The mock executes synchronously. Timeout is passed through the interface but
    real timeout enforcement belongs to a future network transport.
    """
    def __init__(self, transport, ledger, *, timeout_seconds=30):
        if type(transport) is not MockTransport:
            raise ValueError('Paid/live transports are disabled')
        if not 0 < timeout_seconds <= 120: raise ValueError('Invalid timeout')
        self.transport, self.ledger, self.timeout = transport, ledger, timeout_seconds

    def analyse(self, role, snapshot, *, request_id, maximum_microeur, now: datetime):
        request = {'role': role.value, 'prompt_version': VERSION,
                   'instruction': instruction(role), 'snapshot': snapshot.model_dump(mode='json'),
                   'snapshot_id': snapshot.digest(), 'response_schema': RoleReport.model_json_schema()}
        # Reservations remain charged at their maximum when usage is unknown.
        self.ledger.reserve(request_id, maximum_microeur, now)
        reply = self.transport.complete(request, timeout_seconds=self.timeout)
        if not isinstance(reply, ModelReply): raise ValueError('Invalid model reply')
        self.ledger.settle(request_id, reply.cost_microeur)
        if len(reply.text) > 100_000: raise ValueError('Model response too large')
        report = RoleReport.model_validate(json.loads(reply.text))
        if report.role != role or report.snapshot_id != snapshot.digest():
            raise ValueError('Model response identity mismatch')
        if any(f.source_id not in snapshot.source_ids for f in report.findings):
            raise ValueError('Unknown evidence source')
        return report


class GatewayAgent:
    """Mock gateway-backed specialist; final aggregation remains deterministic."""
    def __init__(self, role, gateway, *, run_id, now, maximum_microeur=10):
        from .roles import AgentRole
        if type(gateway) is not ModelGateway: raise ValueError('Unsupported gateway')
        self.role = AgentRole(role)
        self.gateway, self.run_id, self.now, self.maximum = gateway, run_id, now, maximum_microeur

    def analyse(self, snapshot):
        return self.gateway.analyse(self.role, snapshot,
            request_id=f'{self.run_id}:{self.role.value}', maximum_microeur=self.maximum, now=self.now)

    def adjudicate(self, reports, debate):
        from .paper_team import SimulatedAgent
        return SimulatedAgent(self.role).adjudicate(reports, debate)

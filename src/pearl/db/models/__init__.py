"""SQLAlchemy ORM models - import all to register with Base.metadata."""

from pearl.db.models.project import ProjectRow
from pearl.db.models.org_baseline import OrgBaselineRow
from pearl.db.models.app_spec import AppSpecRow
from pearl.db.models.environment_profile import EnvironmentProfileRow
from pearl.db.models.compiled_package import CompiledPackageRow
from pearl.db.models.task_packet import TaskPacketRow
from pearl.db.models.finding import FindingRow, FindingBatchRow
from pearl.db.models.remediation_spec import RemediationSpecRow
from pearl.db.models.approval import ApprovalRequestRow, ApprovalDecisionRow
from pearl.db.models.approval_comment import ApprovalCommentRow
from pearl.db.models.exception import ExceptionRecordRow
from pearl.db.models.job import JobRow
from pearl.db.models.idempotency import IdempotencyKeyRow
from pearl.db.models.report import ReportRow
from pearl.db.models.promotion import (
    PromotionGateRow,
    PromotionEvaluationRow,
    PromotionHistoryRow,
    PromotionPipelineRow,
)
from pearl.db.models.scan_target import ScanTargetRow
from pearl.db.models.fairness import (
    FairnessCaseRow,
    FairnessRequirementsSpecRow,
    EvidencePackageRow,
    FairnessExceptionRow,
    MonitoringSignalRow,
    ContextContractRow,
    ContextPackRow,
    ContextReceiptRow,
    AuditEventRow,
)
from pearl.db.models.governance_telemetry import (
    ClientAuditEventRow,
    ClientCostEntryRow,
)
from pearl.db.models.notification import NotificationRow
from pearl.db.models.integration import (
    IntegrationEndpointRow,
    IntegrationSyncLogRow,
)
from pearl.db.models.user import UserRow, ApiKeyRow
from pearl.db.models.policy_version import PolicyVersionRow
from pearl.db.models.org import OrgRow
from pearl.db.models.business_unit import BusinessUnitRow
from pearl.db.models.org_env_config import OrgEnvironmentConfigRow
from pearl.db.models.framework_requirement import FrameworkRequirementRow

__all__ = [
    "ProjectRow",
    "OrgBaselineRow",
    "AppSpecRow",
    "EnvironmentProfileRow",
    "CompiledPackageRow",
    "TaskPacketRow",
    "FindingRow",
    "FindingBatchRow",
    "RemediationSpecRow",
    "ApprovalRequestRow",
    "ApprovalDecisionRow",
    "ApprovalCommentRow",
    "ExceptionRecordRow",
    "JobRow",
    "IdempotencyKeyRow",
    "ReportRow",
    "PromotionGateRow",
    "PromotionEvaluationRow",
    "PromotionHistoryRow",
    "PromotionPipelineRow",
    "FairnessCaseRow",
    "FairnessRequirementsSpecRow",
    "EvidencePackageRow",
    "FairnessExceptionRow",
    "MonitoringSignalRow",
    "ContextContractRow",
    "ContextPackRow",
    "ContextReceiptRow",
    "AuditEventRow",
    "ScanTargetRow",
    "ClientAuditEventRow",
    "ClientCostEntryRow",
    "NotificationRow",
    "IntegrationEndpointRow",
    "IntegrationSyncLogRow",
    "UserRow",
    "ApiKeyRow",
    "PolicyVersionRow",
    "OrgRow",
    "BusinessUnitRow",
    "OrgEnvironmentConfigRow",
    "FrameworkRequirementRow",
]

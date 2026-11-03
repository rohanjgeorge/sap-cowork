"""Logical context fields, independent of any storage implementation."""

DOMAIN_FIELDS = {
    "FUNCTIONAL_PROCESS": "functional_process_context",
    "SAP_FUNCTIONAL": "sap_functional_context",
    "SAP_TECHNICAL": "sap_technical_context",
    "STANDARDS_GOVERNANCE": "standards_governance_context",
    "HISTORICAL_DEVELOPMENT": "historical_context",
    "SDLC": "sdlc_context",
    # V1 aliases retained to read existing project knowledge.
    "BUSINESS": "business_context",
    "SAP": "sap_context",
    "ORGANIZATION": "organization_context",
}

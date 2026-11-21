export type Urgency = "critical" | "high" | "medium" | "low" | "none";
export type Department = "Duty Ops" | "Sourcing" | "Billing" | "Sales";
export type IssueStatus = "open" | "resolved" | "awaiting_info";
export type Channel = "phone" | "whatsapp" | "none";
export type DatasetName = "supplied" | "harder";

export interface MessageItem {
  event_id: string;
  received_at_ist: string | null;
  thread_id: string | null;
  booking_id: string | null;
  channel: string | null;
  sender: string | null;
  message: string;
  text_normalised: string;
  is_internal: boolean;
}

export interface BookingFacts {
  booking_closed: boolean;
  arrival_confirmed: boolean | null;
  substitute_confirmed: boolean | null;
  confirmed_start_time: string | null;
  refund_status: "approved" | "under_review" | "no_record";
  refund_amount: string | null;
  payment_amount: string | null;
  payout_date: string | null;
  payout_date_recorded: boolean;
  sourcing_checking: boolean;
}

export interface BookingRecord {
  booking_id: string;
  service: string | null;
  locality: string | null;
  scheduled_start_ist: string | null;
  updated_at_ist: string | null;
  operations_record: string | null;
  billing_record: string | null;
  facts: BookingFacts;
  row_number: number;
}

export interface BookingMatch {
  status: "matched" | "unknown_reference" | "no_reference";
  booking_id: string | null;
  possible_candidates: string[];
  note: string;
}

export interface IssueGroup {
  issue_id: string;
  thread_ids: string[];
  booking_id: string | null;
  source_message_ids: string[];
  grouping_reasons: string[];
  booking_match: BookingMatch;
}

export interface EvidenceItem {
  source_id: string;
  kind: "message" | "booking" | "rule";
  quote: string;
}

export interface GuardrailEvent {
  rule_id: string;
  field: string;
  original: unknown;
  enforced: unknown;
  reason: string;
}

export interface Recommendation {
  issue_category: string;
  customer_intent: string;
  status: IssueStatus;
  urgency: Urgency;
  priority_rank: number | null;
  priority_reason: string;
  responsible_department: Department;
  supporting_departments: Department[];
  action_code: string;
  next_action: string;
  contact_channel: Channel;
  missing_information: string[];
  draft_response: string | null;
  hold_contact_reason: string | null;
  explanation: string;
  evidence: EvidenceItem[];
  human_review_required: boolean;
  human_review_reasons: string[];
  guardrail_events: GuardrailEvent[];
  source: "rules" | "ai_guarded" | "ai_raw" | "rules_fallback" | "human";
  confidence: number | null;
  deadline: string | null;
}

export interface IssueResult {
  issue_id: string;
  group: IssueGroup;
  messages: MessageItem[];
  booking: BookingRecord | null;
  rules: Recommendation;
  ai_raw: Recommendation | null;
  ai_guarded: Recommendation | null;
  ai_status: "not_run" | "ok" | "failed" | "skipped";
  ai_error: string | null;
  ai_call_id: string | null;
  final: Recommendation;
}

export interface ReviewRecord {
  review_id: number;
  issue_id: string;
  run_id: string;
  created_at: string;
  action: string;
  reviewer: string;
  reason: string | null;
  urgency?: Urgency | null;
  department?: Department | null;
  action_code?: string | null;
  next_action?: string | null;
  draft_response?: string | null;
  info_requested?: string | null;
  before: Record<string, unknown>;
}

export interface DQIssue {
  source_file: string;
  record_id: string;
  field: string;
  original_value: string | null;
  normalised_value: string | null;
  issue_type: string;
  problem: string;
  severity: "info" | "warning" | "error";
  recommended_action: string;
  human_review_required: boolean;
}

export interface OverviewResponse {
  dataset: DatasetName;
  snapshot_time_ist: string;
  run_id: string;
  mode: "rules" | "ai";
  variant: string;
  run_status: string;
  model: string | null;
  openrouter_configured: boolean;
  notes: string[];
  metrics: {
    total_messages: number;
    total_bookings: number;
    distinct_issues: number;
    urgent_cases: number;
    critical_cases: number;
    high_cases: number;
    open_issues: number;
    resolved_issues: number;
    human_review_cases: number;
    data_quality_issues: number;
    dq_warnings_errors: number;
    human_reviews_logged: number;
  };
  first_callback: {
    issue_id: string;
    booking_id: string | null;
    priority_rank: number | null;
    urgency: Urgency;
    department: Department;
    channel: Channel;
    action_code: string;
    next_action: string;
    source_message_ids: string[];
    deadline: string | null;
    why_first: string;
    draft_response: string | null;
  } | null;
  urgency_breakdown: { urgency: string; count: number }[];
  department_breakdown: { department: string; count: number }[];
  status_breakdown: { status: string; count: number }[];
  recent_runs: {
    run_id: string;
    dataset: string;
    mode: string;
    variant: string;
    model: string | null;
    status: string;
    finished_at: string;
  }[];
}

export interface MethodMetrics {
  variant: string;
  label: string;
  mode: "rules" | "ai";
  status: "evaluated" | "pending_credentials" | "failed";
  note: string;
  model: string | null;
  total_cases: number;
  correct_next_actions: number;
  unsupported_promises: number;
  department_correct: number;
  urgency_correct: number;
  status_correct: number;
  missing_info_complete: number;
  grouping_correct: number;
  first_callback_correct: boolean | null;
  first_callback_actual: string[];
  other_errors: string[];
  token_usage_total: number | null;
  actual_cost_usd: number | null;
  duration_ms_total: number | null;
}

export interface MethodCaseOutcome {
  matched_issue_id: string | null;
  action_code: string | null;
  contact_channel: string | null;
  department: string | null;
  urgency: string | null;
  status: string | null;
  action_correct: boolean;
  department_correct: boolean;
  urgency_correct: boolean;
  status_correct: boolean;
  missing_info_ok: boolean;
  grouping_ok: boolean;
  unsupported_promises: string[];
  notes: string[];
}

export interface EvaluationReport {
  eval_id: string;
  dataset: DatasetName;
  snapshot_time_ist: string;
  evaluated_at: string;
  expected_file: string;
  total_cases: number;
  expected_first_callback: string[];
  human_corrections_count: number;
  methods: MethodMetrics[];
  case_comparisons: {
    source_message_ids: string[];
    booking_id: string | null;
    expected_category: string;
    expected_action_code: string;
    expected_channel: string;
    expected_department: string;
    expected_urgency: string;
    expected_status: string;
    must_flag_missing: string[];
    rationale: string;
    outcomes: Record<string, MethodCaseOutcome>;
  }[];
  disagreements_and_failures: {
    source_message_ids: string[];
    booking_id: string | null;
    variant: string;
    kind: string;
    expected: string;
    actual: string;
    explanation: string;
  }[];
  improvement_summary: {
    before_variant: string;
    after_variant: string;
    before_correct: number;
    after_correct: number;
    total: number;
    delta_correct: number;
    before_unsupported_promises: number;
    after_unsupported_promises: number;
    change_description: string;
  };
  sample_llm_requests: Record<string, unknown>[];
  limitations: string[];
}

export interface ModelStatusResponse {
  provider: string;
  base_url: string;
  model: string;
  api_key_configured: boolean;
  allow_live_ai: boolean;
  timeout_seconds: number;
  max_retries: number;
  temperature: number;
  pricing_assumptions_usd_per_1m: {
    input: number | null;
    output: number | null;
    note: string;
  };
  recent_calls: {
    call_id: string;
    issue_id: string | null;
    ok: boolean;
    provider: string;
    model_requested: string;
    model_used: string | null;
    started_at: string;
    duration_ms: number;
    attempts: number;
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
    cost_usd: number | null;
    error_type: string | null;
    error_message: string | null;
    simulated: boolean;
  }[];
}



# RFC-001: AI Inventory assistant
## status
Draft

## Problem Statement
Users currently need to navigate inventory lists and apply filters manually to identify expiring products or determine which items need replenishment. A natural language interface would simplify accessing this information.

## Goals
* The backend must authenticate users and verify household membership before retrieving inventory data. The LLM must never make authorization decisions.
* Only authorized users are allowed to make a query about the inventory.
* The assistant uses the frontend’s currently selected household.
* Long-term conversational memory is excluded from v1.
* Authenticated users with right persmission should be able to ask to get the list of expiring items within a configurable number of days

  


## Non-Goals
- Inventory Mutations (Read-Only Access): The assistant will not add, update, or delete inventory items (e.g., "Mark milk as finished" or "Add 2 apples"). Supporting write operations introduces confirmation UX and rollback complexity that is deferred to v2.

- Do not generate a shopping list or place an order automatically.
- Long-Term Conversational Memory: Context will only be retained within a single active session. 
- Proactive Notifications & Alerts: The assistant is strictly pull-based (user-initiated queries). Automated push notifications or scheduled digests for expiring items will continue to be handled by the existing notification service.



## Non-Functional Requirements

- For standard queries (up to 1,500 input tokens and 250 output tokens), the complete, non-streamed end-to-end response—measured from API gateway request receipt to final response payload delivery—must be ≤ 3.0 seconds at p95 (with a target median/p50 of ≤ 1.8 seconds).
- If the LLM provider is unavailable, experiences a timeout, or returns a service error, the system must gracefully degrade by returning a structured, text-based inventory list instead of failing entirely.
- Authentication and authorization (checking user permissions and household membership) must be strictly validated within the backend service on every request, independent of any context provided by the LLM layer.
- Implement dual-tier rate limiting on AI query endpoints to control LLM operational costs and prevent abuse:

    * Rolling Window Limit: Maximum of 2 requests per 5 minutes per user per household. Response with 429 error on violating the limit. ENABLE RETRY AFTER 15 MINUTES. 
    * Daily Quota: A maximum cap on daily requests per user/household would be 10 requests/day

- The system estimates or calculates input tokens. If the inventory payload exceeds the maximum input token limit (e.g., 2,000 tokens), older  or paginated to prevent context overflow.
- Per household input/output token should be restricted to 10000 tokens for each per month.
- All assistant requests must be securely logged, recording the user ID, timestamp, household ID, and request type (without logging sensitive personal data in plain text).
- The system must collect LLM usage metrics, including input/output token counts, model identifier, estimated request cost, latency, provider errors, and fallback frequency. Aggregated metrics must support daily and monthly cost monitoring without exposing sensitive inventory data.

## Proposed Architecture

The AI Inventory Assistant will use a **backend-first architecture**. The backend is responsible for authentication, authorization, intent recognition, inventory retrieval, and enforcing business rules. The LLM is used optionally to generate natural-language responses from verified inventory data.

### Request Processing Flow

```text
User Query (React Frontend)
    ↓
FastAPI Request Validation
    ↓
Authentication + Household Authorization
    ↓
Rate Limiting
    ↓
Intent Recognition + Parameter Extraction
    ↓
Query PostgreSQL (Household-Scoped)
    ↓
Structured Inventory Results
    ↓
Token Budget and Cost Validation
    ↓
LLM Response Generation (Optional)
    ↓
Structured API Response
```

### 1. Request Ingestion and Validation

The React frontend sends the user's natural-language query, authentication credentials, and currently selected household ID to the FastAPI backend.

The backend validates the request schema using Pydantic.

### 2. Authentication and Authorization

The backend authenticates the user and verifies that they have permission to read inventory belonging to the requested household.

- Authentication failures return HTTP 401.
- Authorization failures return HTTP 403.
- Household membership must be validated independently of the frontend.
- The LLM must never make authorization decisions.

### 3. Rate Limiting

The backend enforces configurable request limits before processing AI queries.

Initial limits:

- Maximum 2 requests per rolling 5-minute window per user and household.
- Maximum 10 requests per day per user and household.

Requests exceeding these limits return HTTP 429 with an appropriate `Retry-After` header.

### 4. Intent Recognition and Parameter Extraction

The backend identifies supported inventory query types and extracts parameters without relying on an LLM for v1.

For example:

**User query:** "Which products expire within the next seven days?"

**Extracted intent:**

```json
{
  "intent": "expiring_items",
  "parameters": {
    "days": 7
  }
}
```

The backend validates extracted parameters against predefined constraints.

Unsupported or ambiguous queries return a structured response indicating that the request cannot be interpreted.

### 5. Inventory Retrieval

After identifying the query intent, the backend retrieves relevant inventory data from PostgreSQL.

- Queries must be scoped to the authorized household.
- Filtering and sorting are performed in PostgreSQL.
- Only fields required for the requested operation are retrieved.
- Large result sets use explicit pagination.
- The API must not silently omit matching inventory records.

For expiry queries, the backend retrieves inventory item names, quantities, and expiration dates.

### 6. Token Budget and Cost Validation

Before invoking the LLM, the backend:

- Estimates the input token count.
- Enforces a maximum of 2,000 input tokens and 250 output tokens per request.
- Checks the household's remaining monthly token budget.
- Checks configured monetary spending limits.
- Reserves estimated usage atomically to prevent concurrent requests from exceeding budgets.

If the retrieved inventory exceeds the permitted context size, the backend uses explicit pagination or returns structured results without LLM formatting.

Inventory records must never be silently truncated.

### 7. LLM Response Generation

The backend optionally calls OpenAI or Gemini to generate a natural-language summary using the retrieved inventory data.

The LLM receives:

- System instructions defining its permitted behavior.
- The user's validated query.
- Only the relevant, authorized inventory records.

The LLM must not execute database queries, modify inventory, or determine authorization.

The backend validates the generated response before returning it.

### 8. Circuit Breaker and Graceful Degradation

The backend uses explicit timeouts and circuit-breaker protection for LLM provider calls.

Circuit-breaker states:

- **Closed:** Requests are forwarded to the LLM provider.
- **Open:** Provider calls are temporarily bypassed.
- **Half-open:** Limited requests test provider recovery.

If the LLM provider is unavailable, times out, or is temporarily blocked by the circuit breaker, the backend returns structured inventory results for successfully interpreted queries.

If PostgreSQL is unavailable, the backend returns a controlled service error instead of fabricating results.

### 9. Usage Logging and Cost Attribution

The system records:

- Input and output token usage.
- LLM provider and model.
- Estimated monetary cost.
- Request latency.
- Provider errors and fallback events.
- Household-level token consumption.

Token reservations are reconciled against actual usage after each provider response.

Logs must not expose credentials, raw prompts, or sensitive inventory contents by default.

### 10. Response Delivery

The backend returns a structured response containing:

- Recognized intent.
- Validated query parameters.
- Retrieved inventory results.
- Optional LLM-generated summary.
- Pagination metadata when applicable.
- An indicator showing whether fallback behavior was used.

The frontend renders the results and optional summary.

## API Design

``` text
HTTP
POST /api/v1/households/{household_id}/assistant/query
Authorization: Bearer <token>
Content-Type: application/json

JSON
{
  "query": "Which products expire in the next 7 days?",
  "timezone": "Europe/Berlin",
  "page": 1,
  "page_size": 20,
  "generate_summary": true
}

```

### Request Schema

`household_id` is a UUID mapping to the existing home ID. The backend verifies
membership on every request. Credentials and user IDs are not body fields.

| Field | Type | Validation/default |
| --- | --- | --- |
| `query` | string | Required; trim whitespace; 1–1,000 characters after trimming |
| `timezone` | string | Required; valid IANA timezone from the frontend's local timezone, e.g. `Europe/Berlin`; invalid values return `422` |
| `page` | integer | Minimum 1; default 1 |
| `page_size` | integer | 1–100; default 20 |
| `generate_summary` | boolean | Default `true`; `false` bypasses the provider |

Reject unknown fields. Intent and parameters are derived and validated by the
backend. For `expiring_items`, `days` must be 1–365. An ambiguous or missing time
window requires clarification.

### Completed Response — HTTP 200

```json
{
  "status": "completed",
  "household_id": "aeb2389f-2b35-4cc8-8403-850318214795",
  "intent": "expiring_items",
  "parameters": {"days": 7},
  "as_of_date": "2026-11-17",
  "timezone": "Europe/Berlin",
  "message": "Found 1 matching inventory item.",
  "summary": "Your milk expires in two days.",
  "summary_scope": "page",
  "fallback_used": false,
  "fallback_reason": null,
  "inventory": {
    "count": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1,
    "has_next": false,
    "has_previous": false,
    "results": [
      {
        "id": "c5600bcd-18b9-43ec-9717-aac35d90906d",
        "product_id": "e5887442-c684-407c-9470-88841a391af4",
        "name": "Milk",
        "quantity": 1,
        "unit": "pcs",
        "expiry_date": "2026-11-19"
      }
    ]
  }
}
```

- IDs are UUIDs, quantity is an integer, names/units are strings, and dates use
  `YYYY-MM-DD`, consistent with existing inventory types.
- `message` is deterministic backend text. `summary` is optional model-generated
  text. Structured results and counts are authoritative.
- Proposed expiry semantics: positive quantity and expiry date between
  `as_of_date` and `as_of_date + days`, inclusive. Already expired items are
  excluded. The backend computes `as_of_date` from the current instant in the
  validated request timezone and echoes that timezone in the response. Calendar-day
  arithmetic respects local dates across daylight-saving changes. Expiry dates
  remain date-only values and are not converted between timezones.
- Any response timestamps must include the local UTC offset in ISO 8601 format
  (e.g. `2026-11-17T14:30:00+01:00`); never return an ambiguous timezone-free
  timestamp. Stored operational timestamps remain UTC.
- Order results by expiry date, then item ID. `count` covers all matches;
  `results` contains only the requested page. Summaries cover only that page.
- When absent, `summary` and `summary_scope` are both `null`. No matches returns
  an empty results list, count zero, and total pages zero. An out-of-range page
  returns an empty list with the actual count and total pages.
- `has_next` means `page < total_pages`; `has_previous` means `page > 1` and
  at least one preceding page exists.
- To paginate, repeat the POST with the same query and another page number.
  Each request is authorized and rate-limited. Pagination reflects live inventory,
  not a snapshot. Clients should normally disable summary generation when paging.

### Fallback Response

Return the same completed response and inventory data with `summary: null`,
`summary_scope: null`, and `fallback_used: true`. `fallback_reason` is one of:

- `provider_timeout`
- `provider_unavailable`
- `circuit_open`
- `budget_exhausted`
- `context_limit_exceeded`
- `invalid_summary`

When `generate_summary` is false, `fallback_used` is false and the reason is null.
Model/provider details and usage accounting remain internal.

### Clarification and Unsupported Queries — HTTP 200

```json
{
  "status": "clarification_required",
  "household_id": "aeb2389f-2b35-4cc8-8403-850318214795",
  "intent": "expiring_items",
  "message": "Within how many days should items expire?"
}
```

`intent` may be null if it cannot be identified. Unsupported queries use
`status: "unsupported_query"`, `intent: null`, and a message describing supported
read-only questions. Neither variant retrieves inventory or invokes the provider.
The frontend submits a new self-contained query after clarification; this endpoint
does not establish server-side conversation memory. Response schemas form a
discriminated union on `status`.

### Error Responses

| HTTP status | Meaning |
| --- | --- |
| `401` | Missing, invalid, or expired credentials |
| `403` | No membership/read access to the household |
| `422` | Invalid path/body fields; retain FastAPI's validation error response |
| `429` | Request rate or daily request quota exceeded; include `Retry-After` in seconds |
| `503` | Inventory data or required authorization/limit infrastructure unavailable |

New domain errors use the existing `error`, `message`, `details` envelope and
shared `ErrorCode` conventions. Authentication errors retain the existing auth
contract. Provider failure alone does not return `503` when inventory results are
available. Errors must not disclose another household's existence or data.


| Intent Name |Trigger Examples |Extracted| ParametersValidation Rules|
| --- | --- | --- | --- |
|expiring_items |"expiring in next 7 days", "what goes bad soon"days| (int, default 7) |1 <= days <= 365|


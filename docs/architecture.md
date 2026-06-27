# Architecture

## Component Diagram

```mermaid
graph TB
    Client["Client Application"]

    subgraph Gateway["LLM Guardrails Gateway"]
        MW["Middleware\n(RequestContext, ErrorHandler, CORS)"]
        API["API Layer\n/chat  /validate  /health  /policies"]
        GW["GatewayService\n(orchestrator)"]

        subgraph InputLayer["Input Guardrails"]
            PI["PromptInjection"]
            JB["Jailbreak"]
            PII["PII"]
            SEC["Secrets"]
            TOK["TokenLength"]
            LANG["Language"]
            TOX_IN["Toxicity"]
        end

        subgraph OutputLayer["Output Guardrails"]
            JSON_S["JSONSchema"]
            TOX_OUT["Toxicity"]
            PL["PromptLeakage"]
            SL["SecretLeakage"]
            OT["OffTopic"]
            HALL["Hallucination"]
        end

        RE["RetryEngine"]
        PC["PromptCorrector"]
        PF["ProviderFactory"]
        PS["PolicyService\n(YAML hot reload)"]
    end

    subgraph Providers["LLM Providers (via LiteLLM)"]
        OAI["OpenAI"]
        ANT["Anthropic"]
        GEM["Gemini"]
        OLL["Ollama"]
    end

    POLICIES["policies/*.yaml"]

    Client -->|HTTP POST /chat| MW
    MW --> API
    API --> GW
    GW --> InputLayer
    GW --> PF
    PF --> Providers
    GW --> OutputLayer
    OutputLayer -->|fail| RE
    RE --> PC
    RE --> PF
    PS -->|load/watch| POLICIES
    GW --> PS
```

---

## Sequence Diagram — /chat Request

```mermaid
sequenceDiagram
    participant C as Client
    participant MW as Middleware
    participant GW as GatewayService
    participant PS as PolicyService
    participant IV as InputValidator
    participant PF as ProviderFactory
    participant LLM as LLM Provider
    participant OV as OutputValidator
    participant RE as RetryEngine

    C->>MW: POST /chat {prompt, policy_id}
    MW->>MW: attach request_id
    MW->>GW: chat(request, request_id)

    GW->>PS: get(policy_id)
    PS-->>GW: Policy

    GW->>IV: validate_with_policy(prompt, policy)
    IV-->>GW: ValidationResult

    alt input blocked
        GW-->>C: ChatResponse {input_valid: false, response: fallback}
    end

    GW->>PF: get_provider(model)
    PF-->>GW: LLMProvider

    GW->>LLM: complete(messages)
    LLM-->>GW: ProviderResponse

    GW->>OV: validate_with_policy(response, policy)
    OV-->>GW: ValidationResult

    alt output passes
        GW-->>C: ChatResponse {output_valid: true}
    else output fails and retries > 0
        GW->>RE: run(context, provider)
        loop up to max_attempts
            RE->>RE: build_correction(prompt, violations)
            RE->>LLM: complete(corrected_messages)
            LLM-->>RE: ProviderResponse
            RE->>OV: validate_with_policy(response, policy)
            alt passes
                RE-->>GW: (response, result, attempts)
            end
        end
        alt max retries exceeded
            GW-->>C: ChatResponse {response: fallback, output_valid: false}
        else succeeded
            GW-->>C: ChatResponse {output_valid: true, retries: N}
        end
    end
```

---

## Sequence Diagram — Policy Hot Reload

```mermaid
sequenceDiagram
    participant FS as File System
    participant HW as HotReloadWatcher
    participant PS as PolicyService
    participant GW as GatewayService

    FS->>HW: file modified event (policies/default.yaml)
    HW->>PS: reload_one("default")
    PS->>FS: read YAML
    FS-->>PS: raw content
    PS->>PS: parse + validate (Pydantic)
    PS->>PS: update in-memory cache
    Note over GW: next request gets updated policy
```

---

## Design Decisions

**Clean Architecture layers**
- `app/api` — HTTP concerns only (routing, serialisation, auth)
- `app/services` — orchestration and use cases
- `app/guardrails` — pure validation logic, no FastAPI imports
- `app/providers` — external provider abstraction
- `app/policies` — configuration loading and watching

**Strategy pattern for guardrails**
Every guardrail implements `BaseGuardrail.check(text, context) → ValidationResult`. Adding a new guardrail is adding one file; no changes to the calling service.

**Factory pattern for providers**
`ProviderFactory.get_provider(model_string)` returns an `AbstractLLMProvider`. LiteLLM resolves the actual API from the model prefix (`openai/`, `anthropic/`, etc.), so adding a new provider requires zero new code.

**Dependency injection container**
A single `Container` object is constructed at startup and shared across all requests via `get_container()`. This makes unit testing trivial — tests construct the services directly with mocks.

**Immutable policy per request**
`GatewayService` calls `policy_service.get()` at the start of each request. The returned `Policy` is a Pydantic model (immutable value object). Hot reload only updates the registry; in-flight requests are unaffected.

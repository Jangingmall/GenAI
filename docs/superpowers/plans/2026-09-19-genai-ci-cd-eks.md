# GenAI CI/CD·EKS 인계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a test-gated, OIDC-based two-image ECR workflow and complete the chatbot runtime contracts required for the GenAI EKS handoff.

**Architecture:** The workflow uses one service matrix with separate test and Docker paths for `page_generation` and `chat_bot`. PRs validate tests and Docker definitions without AWS credentials; main pushes use immutable commit-SHA tags and reuse an existing ECR digest on reruns. The chatbot keeps `/ai/health` as the existing liveness contract, adds `/ai/ready` for DB/model/LLM readiness, and reads `DB_PASSWORD_FILE` before `DB_PASSWORD`.

**Tech Stack:** GitHub Actions, Docker Buildx, AWS ECR/OIDC, Python 3.11/3.13, FastAPI, pytest, SentenceTransformers, Ollama/SGLang/MLX Serve HTTP contracts.

**Spec:** `docs/superpowers/specs/2026-09-19-genai-ci-cd-eks-design.md`

## Global Constraints

- Build contexts and Dockerfiles must be exactly `page_generation` + `page_generation/deploy/sglang/Dockerfile` and `chat_bot` + `chat_bot/Dockerfile`.
- Platforms must be `linux/amd64`.
- ECR repositories are `jangin-ai/sglang` and `jangin-ai/ollama`.
- Use `ap-northeast-2`, `vars.AWS_ROLE_ARN`, `contents: read`, and `id-token: write` for publish.
- Tags are `${GITHUB_SHA}` only; never publish `latest` or overwrite/delete immutable tags.
- Do not add an LLM server to `chat_bot/Dockerfile`.
- Preserve `GET /ai/health`; add readiness without loading the full embedding model.
- Do not modify the separate `Team3_EcommerceSystemAI` working tree.

---

### Task 1: Establish the chatbot password-file contract

**Files:**
- Modify: `chat_bot/app/config.py`
- Test: `chat_bot/tests/test_config.py`

**Interfaces:**
- Produces: `_read_db_password() -> str`, with `DB_PASSWORD_FILE` taking precedence over `DB_PASSWORD`.

- [ ] **Step 1: Write the failing tests**

```python
def test_db_password_file_takes_precedence(monkeypatch, tmp_path):
    secret = tmp_path / "password"
    secret.write_text("from-file\n", encoding="utf-8")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(secret))
    monkeypatch.setenv("DB_PASSWORD", "from-env")
    assert config._read_db_password() == "from-file"


def test_db_password_file_missing_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PASSWORD_FILE", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="DB_PASSWORD_FILE"):
        config._read_db_password()


def test_db_password_env_is_fallback(monkeypatch):
    monkeypatch.delenv("DB_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("DB_PASSWORD", "from-env")
    assert config._read_db_password() == "from-env"
```

- [ ] **Step 2: Run the focused tests and verify the expected RED failure**

Run: `python -m pytest chat_bot/tests/test_config.py -q` from the GenAI repository root.

Expected: failure because `_read_db_password` does not exist.

- [ ] **Step 3: Implement the minimal reader**

Add a helper that reads the configured file with UTF-8, strips only surrounding line endings/whitespace accepted for a Kubernetes secret, raises `RuntimeError` when the configured file cannot be read, and falls back to `DB_PASSWORD` when no file path is set. Set `Settings.DB_PASSWORD` from that helper during process startup.

- [ ] **Step 4: Run the focused tests and the existing config-dependent suite**

Run: `python -m pytest chat_bot/tests/test_config.py chat_bot/tests/test_main.py -q`.

Expected: all tests pass with no configuration secret required by the test process.

### Task 2: Add dependency-aware chatbot readiness

**Files:**
- Create: `chat_bot/app/readiness.py`
- Modify: `chat_bot/app/main.py`
- Modify: `chat_bot/app/schemas.py`
- Test: `chat_bot/tests/test_readiness.py`
- Test: `chat_bot/tests/test_main.py`

**Interfaces:**
- Produces: `GET /ai/ready` returning `200` with `status=ready` or `503` with `status=not_ready` and a `checks` object.
- Consumes: `settings.DB_*`, `settings.EMBED_MODEL`, `settings.LLM_BACKEND`, backend host/model settings.

- [ ] **Step 1: Write failing unit tests for database, local model, and LLM checks**

```python
def test_readiness_is_not_ready_when_database_check_fails(monkeypatch):
    monkeypatch.setattr(readiness, "_check_database", lambda: (False, "connection failed"))
    monkeypatch.setattr(readiness, "_check_embedding_model", lambda: (True, "configured"))
    monkeypatch.setattr(readiness, "_check_llm", lambda: (True, "model available"))
    result = readiness.check_readiness()
    assert result.status == "not_ready"
    assert result.checks["database"]["ready"] is False


def test_local_embedding_model_requires_modules_and_config(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "EMBED_MODEL", str(tmp_path))
    ready, detail = readiness._check_embedding_model()
    assert ready is False
    assert "modules.json" in detail


def test_sglang_readiness_requires_requested_model(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "sglang")
    monkeypatch.setattr(settings, "SGLANG_HOST", "http://llm")
    monkeypatch.setattr(settings, "LLM_MODEL", "qwen-text")
    monkeypatch.setattr(readiness.requests, "get", lambda *args, **kwargs: FakeResponse({"data": [{"id": "other"}]}))
    ready, _ = readiness._check_llm()
    assert ready is False
```

- [ ] **Step 2: Run the focused readiness tests and verify RED**

Run: `python -m pytest chat_bot/tests/test_readiness.py -q`.

Expected: failure because the readiness module and endpoint do not exist.

- [ ] **Step 3: Implement checks with bounded timeouts**

Implement database `SELECT 1`, local BGE-M3 marker-file validation, and backend-specific model-list checks for Ollama `/api/tags`, SGLang `/v1/models`, and MLX Serve `/v1/models`. Do not import or encode BGE-M3 in a readiness probe. Return structured check details and a boolean aggregate.

- [ ] **Step 4: Expose `/ai/ready` while preserving `/ai/health`**

Add a response model, return HTTP 200 for all ready checks, and return HTTP 503 for any failed check. Keep the current `/ai/health` response model and route unchanged.

- [ ] **Step 5: Run focused and existing API tests**

Run: `python -m pytest chat_bot/tests/test_config.py chat_bot/tests/test_readiness.py chat_bot/tests/test_main.py -q`.

Expected: all pass, including the existing `/ai/health` and lifespan tests.

### Task 3: Record chatbot model and LLM handoff contracts

**Files:**
- Modify: `chat_bot/README-docker.md`
- Modify: `chat_bot/env.example`
- Create: `docs/operations/chatbot-llm-handoff-2026-09-19.md`

**Interfaces:**
- Produces: Native-facing image, model, secret, readiness, and unresolved LLM contract documentation.

- [ ] **Step 1: Document BGE-M3 revision and required files**

Record `BAAI/bge-m3`, revision `5617a9f61b028005a4858fdac845db406aefb181`, 1024 dimensions, the SentenceTransformers file set, and the approximately 2.30 GB repository subset used by the CPU runtime at `/models/bge-m3`.

- [ ] **Step 2: Document API-image and separate-LLM boundaries**

Record that `jangin-ai/ollama` stores only the chatbot API image; the Dockerfile contains no Ollama/SGLang process. Document current Ollama, SGLang, and MLX Serve HTTP contracts and list T4 engine/version/digest/model/precision/command/port/health as an explicit Native/model-owner handoff item rather than inventing values.

- [ ] **Step 3: Document `DB_PASSWORD_FILE` and readiness**

Add `DB_PASSWORD_FILE`, `GET /ai/health`, and `GET /ai/ready` examples, including the required BGE-M3 volume mount and `LLM_MODEL`/backend variables.

- [ ] **Step 4: Run Markdown/link and diff checks**

Run: `git diff --check` and inspect all changed contract sections for consistency with the code and workflow.

### Task 4: Add PR and main ECR workflow

**Files:**
- Create: `.github/workflows/genai-ci.yml`

**Interfaces:**
- Consumes: `vars.AWS_REGION`, defaulting to `ap-northeast-2`, and required `vars.AWS_ROLE_ARN` on main pushes.
- Produces: service test results, build validation, ECR `${GITHUB_SHA}` tags, and digest summaries.

- [ ] **Step 1: Add service test matrix**

Use `ubuntu-24.04`, Python 3.13 plus locked `uv` dependencies for `page_generation`, and Python 3.11 plus `chat_bot/requirements-dev.txt` for `chat_bot`. Append service, source SHA, runner, command, and outcome to `GITHUB_STEP_SUMMARY`.

- [ ] **Step 2: Add PR Docker validation**

Use the exact context and Dockerfile matrix. Run `docker buildx build --check --platform linux/amd64` and a normal push-free amd64 build for both services when capacity permits. If the page PR runner has less than 35 GiB free, keep the definition check green, write a warning Summary, and skip only the full page build. Do not configure AWS credentials, ECR login, or push in pull-request jobs.

- [ ] **Step 3: Add main OIDC publish matrix**

After tests, configure AWS credentials with `aws-actions/configure-aws-credentials`, log into ECR, build/push both images with `docker/build-push-action`, and set `platforms: linux/amd64`. Add `contents: read` and `id-token: write` to the publish job only.

- [ ] **Step 4: Implement immutable-tag reuse**

Before building a matrix entry, call `aws ecr describe-images --repository-name "$REPOSITORY" --image-ids imageTag="$GITHUB_SHA"`. If the tag exists, capture its digest and skip the push. If it does not exist, push once and use the build action's digest output. Treat a missing repository or permission error as a hard failure.

- [ ] **Step 5: Add disk preflight and digest Summary**

For page-generation publish, require enough free disk for the measured 15.47GiB image plus BuildKit working layers. Use a 35GiB free-space gate and fail before ECR authentication if `ubuntu-24.04` is insufficient. In PR validation, report the same requirement and skip only the full page build when the runner is too small. Never publish `latest`. Always print image URI, digest, source SHA, execution URL, test result, and whether the digest was pushed or reused.

- [ ] **Step 6: Validate workflow syntax and local paths**

Run a YAML parse check, `docker buildx build --check` for both Dockerfiles, and inspect the workflow matrix for the exact repository paths before running service tests.

### Task 5: Verify all deliverables and handoff state

**Files:**
- Inspect: `.github/workflows/genai-ci.yml`, `chat_bot/`, `page_generation/`
- Inspect: `git status`, `git diff --check`

- [ ] **Step 1: Run the deterministic chatbot suite**

Run: `cd chat_bot && python -m pytest -q -k 'not real_llm'`; the three named `real_llm` cases require an external Ollama instance and remain a separate integration check.

- [ ] **Step 2: Run page-generation tests**

Run: `uv run --project page_generation pytest -q` with the locked development dependency set.

- [ ] **Step 3: Run Docker checks/builds**

Run both `linux/amd64` Docker builds locally when disk is available, measure image size and runtime smoke behavior, and preserve the runner-capacity evidence for the external workflow.

- [ ] **Step 4: Review diff and final handoff**

Run `git diff --check`, verify no BE repository files were changed, list the new workflow and chatbot contract files, and explicitly report that ECR/OIDC/GPU execution remains unverified until Infra supplies the role/registry and GPU runner.

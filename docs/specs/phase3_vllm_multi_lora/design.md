# Phase 3 · vLLM 多 LoRA · Design

---

## 1. 架构

```
HermesBridge.respond(prompt, tenant_id, model_route="lora:tenant_xxx")
    │
    ▼
ModelRouter.route()
    │
    ├─ lora:tenant_xxx → VLLMClient (port 8000)
    ├─ hermes_default  → hermes-agent (port 8317)
    └─ claude_sonnet   → Anthropic API
                            │
                            ▼
                vllm serve Qwen3-8B \
                  --enable-lora \
                  --max-loras 100 \
                  --lora-modules tenant_001=/models/tenant_001/lora \
                                 tenant_002=/models/tenant_002/lora \
                                 ...
```

---

## 2. LoRA Registry

```python
# server/lora_registry.py
class LoRARegistry:
    def __init__(self, models_dir: Path):
        self.models_dir = models_dir
        self._registry: dict[str, Path] = {}

    def scan(self) -> int:
        """扫描 models/{tenant}/lora/ 目录，注册所有 LoRA。"""
        for tenant_dir in self.models_dir.iterdir():
            lora_path = tenant_dir / "lora"
            if (lora_path / "adapter_model.safetensors").exists():
                self._registry[tenant_dir.name] = lora_path
        return len(self._registry)

    def get(self, tenant_id: str) -> Path | None:
        return self._registry.get(tenant_id)

    def register(self, tenant_id: str, lora_path: Path) -> None:
        self._registry[tenant_id] = lora_path

    def list_loaded(self) -> list[str]:
        return list(self._registry.keys())
```

---

## 3. vLLM 客户端封装

```python
# server/vllm_client.py
import openai

class VLLMClient:
    """vLLM 暴露 OpenAI 兼容 API · 用 openai-python 调即可。"""
    def __init__(self, base_url: str = "http://localhost:8000/v1"):
        self.client = openai.AsyncOpenAI(api_key="EMPTY", base_url=base_url)

    async def generate(
        self,
        prompt: str,
        lora_id: str,                   # vLLM 启动时注册的 LoRA 名
        max_tokens: int = 300,
        temperature: float = 0.7,
    ) -> str:
        resp = await self.client.completions.create(
            model=lora_id,                # 用 LoRA 名当 model
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].text.strip()
```

---

## 4. 灰度发布

```python
# server/canary.py
class CanaryController:
    """新 LoRA 上线 → 20% 流量 → 监控 24h → 全量或回滚。"""

    def __init__(self):
        self.canary_loras: dict[str, dict] = {}  # tenant → {old, new, ratio, started_at}

    def start_canary(self, tenant_id: str, old: str, new: str, ratio: float = 0.2):
        self.canary_loras[tenant_id] = {
            "old": old, "new": new, "ratio": ratio,
            "started_at": int(time.time()),
            "metrics": {"accepted": 0, "edited": 0, "rejected": 0},
        }

    def pick_route(self, tenant_id: str) -> str:
        cfg = self.canary_loras.get(tenant_id)
        if not cfg:
            return f"lora:{tenant_id}"
        if random.random() < cfg["ratio"]:
            return cfg["new"]
        return cfg["old"]

    def record_decision(self, tenant_id: str, route: str, decision: str):
        cfg = self.canary_loras.get(tenant_id)
        if cfg and route == cfg["new"]:
            cfg["metrics"][decision] = cfg["metrics"].get(decision, 0) + 1

    def should_promote(self, tenant_id: str, base_acceptance: float) -> bool:
        cfg = self.canary_loras.get(tenant_id)
        if not cfg:
            return False
        m = cfg["metrics"]
        total = sum(m.values())
        if total < 50:
            return False
        new_acceptance = m["accepted"] / total
        return new_acceptance >= base_acceptance - 0.05

    def should_rollback(self, tenant_id: str, base_acceptance: float) -> bool:
        cfg = self.canary_loras.get(tenant_id)
        if not cfg:
            return False
        m = cfg["metrics"]
        total = sum(m.values())
        if total < 30:
            return False
        new_acceptance = m["accepted"] / total
        return new_acceptance < base_acceptance - 0.10
```

---

## 5. Qt6 浮窗

```python
# client/qt6_popup.py
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton

class ReviewWindow(QWidget):
    def __init__(self, suggestion):
        super().__init__()
        self.setWindowTitle(f"白羊建议 · {suggestion.intent.intent.value}")
        self.setFixedSize(420, 200)
        layout = QVBoxLayout()

        layout.addWidget(QLabel(f"客户: {suggestion.inbound_msg_id}"))
        layout.addWidget(QLabel(f"建议: {suggestion.text}"))

        btns = QHBoxLayout()
        for label, decision in [("发送", "accept"), ("改", "edit"), ("拒", "reject"), ("接管", "human_takeover")]:
            b = QPushButton(label)
            b.clicked.connect(lambda _, d=decision: self.on_decision(d))
            btns.addWidget(b)
        layout.addLayout(btns)
        self.setLayout(layout)
        self._decision = None

    def on_decision(self, d: str):
        self._decision = d
        self.close()
```

---

## 6. 部署 yaml

```yaml
# scripts/vllm_systemd.service
[Unit]
Description=Baiyang vLLM Server
After=network.target

[Service]
ExecStart=/opt/baiyang/.venv/bin/vllm serve Qwen/Qwen3-8B-Instruct \
  --enable-lora \
  --max-loras 100 \
  --max-lora-rank 16 \
  --lora-modules ${LORA_MODULES_STR} \
  --port 8000
Restart=on-failure
RestartSec=10s
User=baiyang

[Install]
WantedBy=multi-user.target
```

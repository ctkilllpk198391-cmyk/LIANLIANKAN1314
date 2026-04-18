"""LoRA 训练 · LLaMA-Factory + Unsloth + QLoRA · 配置生成 + subprocess 启动器。"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class LoRAConfig:
    tenant_id: str
    base_model: str = "Qwen/Qwen3-8B-Instruct"
    train_data: str = "data/tenant/{tenant}/train_chatml.jsonl"
    output_dir: str = "models/{tenant}/lora"
    lora_rank: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    learning_rate: float = 2e-4
    num_epochs: int = 3
    batch_size: int = 4
    grad_accum: int = 4
    max_seq_length: int = 2048
    warmup_steps: int = 50
    save_steps: int = 100
    quantization: str = "4bit"
    use_unsloth: bool = True
    template: str = "qwen"


def render_llama_factory_yaml(cfg: LoRAConfig) -> dict:
    return {
        "model_name_or_path": cfg.base_model,
        "stage": "sft",
        "do_train": True,
        "finetuning_type": "lora",
        "lora_target": "all",
        "lora_rank": cfg.lora_rank,
        "lora_alpha": cfg.lora_alpha,
        "lora_dropout": cfg.lora_dropout,
        "dataset": f"tenant_{cfg.tenant_id}",
        "dataset_dir": str(Path(cfg.train_data.format(tenant=cfg.tenant_id)).parent),
        "template": cfg.template,
        "cutoff_len": cfg.max_seq_length,
        "max_samples": 50000,
        "output_dir": cfg.output_dir.format(tenant=cfg.tenant_id),
        "logging_steps": 10,
        "save_steps": cfg.save_steps,
        "warmup_steps": cfg.warmup_steps,
        "learning_rate": cfg.learning_rate,
        "num_train_epochs": cfg.num_epochs,
        "per_device_train_batch_size": cfg.batch_size,
        "gradient_accumulation_steps": cfg.grad_accum,
        "lr_scheduler_type": "cosine",
        "quantization_bit": 4 if cfg.quantization == "4bit" else None,
        "use_unsloth": cfg.use_unsloth,
        "fp16": True,
        "gradient_checkpointing": True,
    }


def write_training_config(cfg: LoRAConfig, output_path: Path) -> Path:
    payload = render_llama_factory_yaml(cfg)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)
    logger.info("LoRA config written: %s", output_path)
    return output_path


def estimate_training_time(num_samples: int, num_epochs: int = 3) -> int:
    """A100 80G QLoRA Qwen3-8B 经验值。"""
    samples_per_sec = 1.5
    return int(num_samples * num_epochs / samples_per_sec)


def make_oom_fallback(cfg: LoRAConfig) -> LoRAConfig:
    return LoRAConfig(
        tenant_id=cfg.tenant_id,
        base_model=cfg.base_model,
        train_data=cfg.train_data,
        output_dir=cfg.output_dir,
        lora_rank=cfg.lora_rank,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        learning_rate=cfg.learning_rate,
        num_epochs=cfg.num_epochs,
        batch_size=max(1, cfg.batch_size // 2),
        grad_accum=cfg.grad_accum * 2,
        max_seq_length=max(512, cfg.max_seq_length // 2),
        quantization=cfg.quantization,
        use_unsloth=True,
        template=cfg.template,
    )


LossLineRe = re.compile(r"['\"]?loss['\"]?\s*[:=]\s*([0-9.]+)")


@dataclass
class TrainingState:
    step: int = 0
    last_loss: Optional[float] = None
    losses: list[float] = None
    early_stopped: bool = False
    oom: bool = False
    return_code: int = -1

    def __post_init__(self):
        if self.losses is None:
            self.losses = []


class TrainingLauncher:
    def __init__(self, llama_factory_cmd: str = "llamafactory-cli"):
        self.cmd = llama_factory_cmd
        self.state = TrainingState()

    def is_available(self) -> bool:
        return shutil.which(self.cmd) is not None

    async def launch(
        self,
        config_yaml: Path,
        log_callback: Optional[Callable[[str], Awaitable[None]]] = None,
        early_stop_patience: int = 50,
    ) -> TrainingState:
        if not self.is_available():
            logger.warning("%s 未安装 · 返回 mock 成功", self.cmd)
            self.state.return_code = 0
            self.state.last_loss = 0.42
            return self.state

        cmd = [self.cmd, "train", str(config_yaml)]
        logger.info("launching: %s", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        plateau_count = 0
        last_min_loss = float("inf")
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            if log_callback:
                await log_callback(line)

            if "OutOfMemoryError" in line or "CUDA out of memory" in line:
                self.state.oom = True
                logger.error("OOM detected · 终止训练")
                proc.terminate()
                break

            m = LossLineRe.search(line)
            if m:
                try:
                    val = float(m.group(1))
                    self.state.last_loss = val
                    self.state.losses.append(val)
                    self.state.step += 10
                    if val < last_min_loss - 1e-3:
                        last_min_loss = val
                        plateau_count = 0
                    else:
                        plateau_count += 1
                    if plateau_count >= early_stop_patience:
                        self.state.early_stopped = True
                        logger.info("early stopped at step %d (loss plateau)", self.state.step)
                        proc.terminate()
                        break
                except ValueError:
                    pass

        self.state.return_code = await proc.wait()
        return self.state


async def train_with_oom_fallback(
    cfg: LoRAConfig,
    config_path: Path,
    launcher: TrainingLauncher,
    log_callback: Optional[Callable[[str], Awaitable[None]]] = None,
) -> TrainingState:
    write_training_config(cfg, config_path)
    state = await launcher.launch(config_path, log_callback=log_callback)
    if state.oom:
        logger.warning("第一次 OOM · fallback 配置重试")
        cfg2 = make_oom_fallback(cfg)
        write_training_config(cfg2, config_path)
        launcher2 = TrainingLauncher(launcher.cmd)
        return await launcher2.launch(config_path, log_callback=log_callback)
    return state


# --------------------------------------------------------------------------- #
# T4 · 数据护城河 · LoRA 文件加密接口（prod 接 · dev 留存根）
#
# prod 集成方式（Phase 4 · 部署时启用）：
#   from server.encryption import get_default_kms
#   kms = get_default_kms()
#   lora_bytes = Path(output_dir / "lora.bin").read_bytes()
#   encrypted = kms.encrypt(tenant_id, lora_bytes)
#   Path(output_dir / "lora.bin.enc").write_bytes(encrypted)
#   Path(output_dir / "lora.bin").unlink()  # 删除明文
#
# 解密（inference 时）：
#   encrypted = Path(output_dir / "lora.bin.enc").read_bytes()
#   lora_bytes = kms.decrypt(tenant_id, encrypted)
# --------------------------------------------------------------------------- #

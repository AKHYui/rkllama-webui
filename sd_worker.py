#!/usr/bin/env python3
"""RKLLM NPU WebUI - 文生图 worker 子进程

独立进程运行 Anything V5 (anime) + LCM 文生图管线（RKNNLite，512x512）。
与 WebUI 通过 stdin/stdout 传输 JSON 消息；被 kill 时全部内存（含模型/torch）
由内核立即回收，与 llm_demo 子进程完全对称。

协议（行分隔 JSON）：
  启动:  stdout -> {"event":"ready"}
  请求:  stdin  <- {"cmd":"generate","id":"...","prompt":"...",
                    "negative_prompt":"...","steps":N,"cfg":F,"seed":N}
  结果:  stdout -> {"event":"result","id":"...","path":"/abs/path.png"}
          或     -> {"event":"error","id":"...","message":"..."}
  退出:  stdin  <- {"cmd":"exit"}
"""

import argparse
import json
import logging
import os
import sys
import time
import uuid

# rknnlite 导入会破坏 logging 的级别名映射（导致后续 `logger.setLevel("WARNING")`
# 报 "Unknown level"）。因此 torch/diffusers/transformers 先导入（安全顺序），
# rknnlite 惰性导入并在其后立即修复 logging。
_LOG_LEVELS = {
    "CRITICAL": 50, "FATAL": 50, "ERROR": 40,
    "WARN": 30, "WARNING": 30, "INFO": 20, "DEBUG": 10, "NOTSET": 0,
}
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(asctime)s [sd_worker] %(message)s")
logging._nameToLevel.update(_LOG_LEVELS)
logger = logging.getLogger("sd_worker")


def _repair_logging():
    logging._nameToLevel.update(_LOG_LEVELS)


def _emit(obj):
    """向 stdout 输出一行 JSON（flush 保证及时）"""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


import numpy as np
from PIL import Image
import torch
from diffusers.schedulers import LCMScheduler
from transformers import CLIPTokenizer


class RKNN2Model:
    """RKNNLite 模型包装：加载 + 推理 + 释放"""

    def __init__(self, model_dir: str, data_format: str = "nchw"):
        self.data_format = data_format.lower()
        self.config = json.load(open(os.path.join(model_dir, "config.json")))
        rknn_path = os.path.join(model_dir, "model.rknn")
        assert os.path.exists(rknn_path), f"Missing {rknn_path}"
        from rknnlite.api import RKNNLite
        _repair_logging()  # rknnlite 导入后立即修复 logging
        self.rknnlite = RKNNLite()
        self.rknnlite.load_rknn(rknn_path)
        self.rknnlite.init_runtime(core_mask=RKNNLite.NPU_CORE_AUTO)

    def __call__(self, **kwargs):
        def prep(x):
            if isinstance(x, np.ndarray):
                if x.dtype in (np.float16, np.float64):
                    x = x.astype(np.float32, copy=False)
                if x.ndim == 4:
                    if self.data_format == "nhwc" and x.shape[1] in (1, 3, 4):
                        x = x.transpose(0, 2, 3, 1)
                    elif self.data_format == "nchw" and x.shape[-1] in (1, 3, 4):
                        x = x.transpose(0, 3, 1, 2)
                x = np.ascontiguousarray(x)
            return x
        inputs = [prep(v) for v in kwargs.values()]
        return self.rknnlite.inference(inputs=inputs, data_format=self.data_format)

    def release(self):
        try:
            self.rknnlite.release()
        except Exception:
            pass


class AnythingV5Pipeline:
    """Anything V5 + LCM 管线（复用原 app.py 逻辑，固定 512x512）"""

    def __init__(self, model_dir: str):
        logger.info("Loading models from %s ...", model_dir)
        self.text_encoder = RKNN2Model(os.path.join(model_dir, "text_encoder"), "nchw")
        self.unet = RKNN2Model(os.path.join(model_dir, "unet"), "nhwc")
        self.vae_decoder = RKNN2Model(os.path.join(model_dir, "vae_decoder"), "nhwc")
        self.tokenizer = CLIPTokenizer.from_pretrained(os.path.join(model_dir, "tokenizer"))
        scfg = json.load(open(os.path.join(model_dir, "scheduler", "scheduler_config.json")))
        self.scheduler = LCMScheduler.from_config(scfg)
        self.unet_config = self.unet.config
        logger.info("All models ready.")

    def _encode(self, text: str):
        inputs = self.tokenizer([text], padding="max_length",
            max_length=self.tokenizer.model_max_length, truncation=True, return_tensors="np")
        return self.text_encoder(input_ids=inputs.input_ids.astype(np.int32))[0]

    def generate(self, prompt, negative_prompt="", num_inference_steps=4,
                 seed=-1, guidance_scale=1.0):
        prompt_embeds = self._encode(prompt)
        do_cfg = guidance_scale > 1.001
        neg_embeds = self._encode(negative_prompt) if do_cfg else None

        self.scheduler.set_timesteps(num_inference_steps)
        timesteps = self.scheduler.timesteps

        sample_size = 64  # fixed: RKNN model compiled for 512x512 -> latent 64x64
        if seed is None or seed < 0:
            rng = np.random
        else:
            rng = np.random.RandomState(seed)
        latents = rng.randn(1, self.unet_config["in_channels"], sample_size, sample_size).astype(np.float32)
        latents = latents * np.float32(self.scheduler.init_noise_sigma)

        for i, t in enumerate(timesteps):
            t_arr = np.array([t], dtype=np.int64)
            noise_pred = self.unet(sample=latents, timestep=t_arr,
                encoder_hidden_states=prompt_embeds)[0]
            if do_cfg:
                noise_neg = self.unet(sample=latents, timestep=t_arr,
                    encoder_hidden_states=neg_embeds)[0]
                noise_pred = noise_neg + guidance_scale * (noise_pred - noise_neg)
            latents_np, _ = self.scheduler.step(torch.from_numpy(noise_pred), t,
                torch.from_numpy(latents), return_dict=False)
            latents = latents_np.numpy()

        latents /= self.vae_decoder.config["scaling_factor"]
        image = self.vae_decoder(latent_sample=latents)[0]
        image = np.clip(image / 2 + 0.5, 0, 1)
        image = image.transpose(0, 2, 3, 1)
        image = (image * 255).round().astype("uint8")
        return Image.fromarray(image[0])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", default="/opt/anything_v5")
    parser.add_argument("--output_dir", default="/opt/rkllama/sd_output")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    try:
        pipeline = AnythingV5Pipeline(args.model_dir)
    except Exception as e:
        _emit({"event": "error", "id": "startup", "message": f"加载模型失败: {e}"})
        logger.exception("startup failed")
        sys.exit(1)

    _emit({"event": "ready"})
    logger.info("ready, waiting for requests")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            _emit({"event": "error", "id": "", "message": "bad request"})
            continue
        cmd = req.get("cmd")
        if cmd == "exit":
            break
        if cmd != "generate":
            continue
        rid = req.get("id", uuid.uuid4().hex[:8])
        try:
            t0 = time.time()
            img = pipeline.generate(
                prompt=req.get("prompt", ""),
                negative_prompt=req.get("negative_prompt", ""),
                num_inference_steps=int(req.get("steps", 4)),
                seed=int(req.get("seed", -1)),
                guidance_scale=float(req.get("cfg", 1.0)))
            path = os.path.join(args.output_dir, f"{rid}.png")
            img.save(path, format="PNG")
            logger.info("generated in %.1fs -> %s", time.time() - t0, path)
            _emit({"event": "result", "id": rid, "path": path})
        except Exception as e:
            logger.exception("generate failed")
            _emit({"event": "error", "id": rid, "message": str(e)})

    logger.info("worker exiting")


if __name__ == "__main__":
    main()
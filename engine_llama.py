"""
RKLLM NPU WebUI - llama.cpp engine
Per-request model load -> generate -> unload
Handles Gemma 4 [Start thinking]/[End thinking] parsing
"""
import asyncio, os, re, time
from config import LLAMA_CLI, LLAMA_LIB_PATH, SAMPLING_PARAMS

THINK_START = "[Start thinking]"
THINK_END = "[End thinking]"

def _parse_thinking_and_response(text):
    """Split thinking and response"""
    p = re.escape(THINK_START) + r"(.*?)" + re.escape(THINK_END)
    m = re.search(p, text, re.DOTALL)
    if m:
        return m.group(1).strip(), text[m.end():].strip()
    return "", text.strip()

def _build_gemma4_prompt(query, system_prompt, history):
    """Build Gemma 4 prompt: each turn = <start_of_turn>role\ncontent<end_of_turn>"""
    nl = chr(10)
    t = []
    if system_prompt:
        t.append("<start_of_turn>user" + nl + system_prompt + "<end_of_turn>")
    for m in history:
        c = (m.get("content") or "").strip()
        if not c: continue
        r = "<start_of_turn>user" if m["role"] == "user" else "<start_of_turn>model"
        t.append(r + nl + c + "<end_of_turn>")
    t.append("<start_of_turn>user" + nl + query + "<end_of_turn>")
    t.append("<start_of_turn>model" + nl)
    return nl.join(t)

async def llama_generate(model_path, query, system_prompt, history, timeout=300):
    """Run llama-cli, parse output"""
    prompt = _build_gemma4_prompt(query, system_prompt, history)
    sp = SAMPLING_PARAMS
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = LLAMA_LIB_PATH + ":" + env.get("LD_LIBRARY_PATH", "")
    cmd = [LLAMA_CLI, "-m", model_path, "-ngl", "99", "-c", "8192", "-n", "1024",
           "--temp", str(sp.get("temperature", 0.7)),
           "--top-p", str(sp.get("top_p", 0.9)),
           "--no-display-prompt", "--simple-io", "-p", prompt]
    print("\n[*] llama-cli: " + os.path.basename(model_path))
    print("[prompt] " + str(len(prompt)) + " chars, " + str(len(history)) + " turns")
    t0 = time.time()
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill(); await proc.wait()
        e = time.time() - t0
        return {"thinking":"","response":"[Timeout]","full_output":"","elapsed":e,"tokens":0}
    e = time.time() - t0
    out = stdout.decode("utf-8", errors="replace").strip()
    thinking, response = _parse_thinking_and_response(out)
    print("[done] " + str(round(e, 1)) + "s, think=" + str(len(thinking)) + "c, resp=" + str(len(response)) + "c")
    return {"thinking":thinking,"response":response,"full_output":out,"elapsed":e,"tokens":0}

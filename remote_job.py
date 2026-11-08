"""Runs ON the Colab VM, uploaded and started by `fluxx gen`. Not meant to run locally.

A worker: installs diffusers, loads FLUX 3 Image Klein and a judge model ONCE, then renders every job
that appears in /content/fluxx/jobs/<id>/spec.json until it has been idle for worker.json's idle_exit_s.
That is what lets `fluxx gen --keep N` reuse a warm GPU without loading anything again.

Per shot it renders up to `candidates` images; the judge (a vision-language model on the same GPU)
scores each against the brief, the product references and the avoid list, and the best one is kept.
Progress goes to progress.json files the local side polls over short `colab exec` calls.
"""
import json
import os
import re
import subprocess
import sys
import time
import traceback
import zipfile

W = "/content/fluxx"
JUDGE_MODEL = "Qwen/Qwen3.5-9B"  # Apache-2.0, same architecture as FLUX 3's prompt upsampler
GOOD_ENOUGH = 9  # stop rendering candidates once one scores this with no defects
JUDGE_PROMPT = """You are a strict art director checking an AI-generated marketing picture before a client sees it.
{refs}The LAST image is the candidate.
Brief: {scene}
Never allowed in the picture: {avoid}
Check, in order:
1. Anatomy: hands, fingers, faces, eyes, limbs.
2. Impossible or duplicated objects: something that exists twice when it should exist once (for example a phone handset held in a hand while another handset still rests on the phone), objects merging or floating.
3. Product fidelity: the product looks like the reference photos (shape, color, materials, details).
4. Readable text, letters, numbers or logos.
5. The brief is followed.
6. Appeal as an advertisement: light, composition, emotion.
{checks}Reply in two parts. First one line starting "Inventory:" that counts what you actually see of the product and
its parts (for example "phone bases: 1, handsets: 2, handset on base: yes"). Then, on its own line, JSON:
{{"score": <integer 0-10, 10 = ready to publish>, "defects": ["short phrase", ...]}}
Any defect from checks 1-4 or from the brand rules caps the score at 5. An empty defects list means none found."""


def write_json(path, obj):
    with open(path + ".tmp", "w") as f:
        json.dump(obj, f)
    os.replace(path + ".tmp", path)


def beat():
    with open(f"{W}/heartbeat", "w") as f:
        f.write(str(time.time()))


def progress(where, **kw):
    write_json(f"{where}/progress.json", kw)
    beat()


def setup(cfg):
    import torch
    progress(W, stage="installing diffusers")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "diffusers>=0.42.1",
                    "transformers", "accelerate", "hf_xet"], check=True)
    tok = f"{W}/hf_token"
    if os.path.exists(tok):  # never printed, removed from disk once read
        os.environ["HF_TOKEN"] = open(tok).read().strip()
        os.remove(tok)
    os.environ["HF_XET_HIGH_PERFORMANCE"] = "1"

    progress(W, stage="downloading and loading FLUX 3")
    from diffusers import ModularPipeline
    repo = cfg["model"]
    if cfg["source"] != repo:
        # A public mirror whose weights fluxx checked against the official sha256 before launch. Its
        # component index still names the gated official repo, so point those entries at the local copy.
        from huggingface_hub import snapshot_download
        repo = snapshot_download(cfg["source"], local_dir="/content/klein", allow_patterns=[
            "modular_model_index.json", "transformer/*", "text_encoder/*", "vae/*"])
        idx_path = f"{repo}/modular_model_index.json"
        idx = json.load(open(idx_path))
        for v in idx.values():
            if isinstance(v, list) and len(v) == 3 and v[2].get("pretrained_model_name_or_path") == cfg["model"]:
                v[2]["pretrained_model_name_or_path"] = repo
        json.dump(idx, open(idx_path, "w"), indent=1)
    if cfg["upsample"]:
        pipe = ModularPipeline.from_pretrained(repo)
    else:  # captions are already complete: skip the 9B prompt upsampler
        blocks = ModularPipeline.from_pretrained(repo).blocks
        blocks.sub_blocks.pop("prompt_upsampler")
        pipe = blocks.init_pipeline(repo)
    pipe.load_components(dtype={"vae": torch.float32, "default": torch.bfloat16})
    pipe.to("cuda")

    judge, note = None, ""
    if cfg.get("judge", True):
        progress(W, stage="loading the judge")
        try:
            from transformers import AutoModelForImageTextToText, AutoProcessor
            judge = (AutoModelForImageTextToText.from_pretrained(JUDGE_MODEL, dtype=torch.bfloat16, device_map="cuda"),
                     AutoProcessor.from_pretrained(JUDGE_MODEL))
        except Exception as e:  # pictures still render, just unjudged
            note = f"judge unavailable: {type(e).__name__}: {e}"[:400]
    return pipe, judge, note


def small(img, side=1024):
    img = img.copy()
    img.thumbnail((side, side))
    return img


def judge_image(judge, img, refs, scene, avoid, checks=()):
    """(score 0-10 or None, defects) from the judge model looking at the references and the candidate."""
    import torch
    model, proc = judge
    rules = "".join(f"- {c}\n" for c in checks)
    text = JUDGE_PROMPT.format(scene=scene, avoid=avoid or "nothing specific",
                               checks=f"7. Brand rules, learned from past mistakes; any broken rule is a defect:\n{rules}" if rules else "",
                               refs=f"The first {len(refs)} image(s) are reference photos of the product.\n" if refs else "")
    content = [{"type": "image", "image": small(r, 768)} for r in refs] + [{"type": "image", "image": small(img)},
                                                                         {"type": "text", "text": text}]
    inputs = proc.apply_chat_template([{"role": "user", "content": content}], add_generation_prompt=True,
                                      tokenize=True, return_dict=True, return_tensors="pt",
                                      enable_thinking=False).to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=400, do_sample=False)
    raw = proc.decode(out[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    try:
        d = json.loads(re.findall(r"\{[^{}]*\}", raw)[-1])  # the last flat JSON object, after the inventory
        defects = [str(x) for x in d.get("defects", []) if str(x).strip()]
        return max(0, min(10, int(d["score"]))), defects
    except (IndexError, ValueError, KeyError, TypeError):
        return None, [f"judge reply unreadable: {raw[:120]}"]


def run_job(pipe, judge, jd):
    import torch
    from PIL import Image
    spec = json.load(open(f"{jd}/spec.json"))
    out = f"{jd}/out"
    os.makedirs(f"{out}/alts", exist_ok=True)
    refs = {p: Image.open(f"{jd}/{p}").convert("RGB") for s in spec["shots"] for p in s["refs"]}
    results, total, t_job = [], len(spec["shots"]), time.time()
    for i, shot in enumerate(spec["shots"]):
        rec = {k: shot[k] for k in ("id", "scene", "width", "height")}
        t = time.time()
        try:
            shot_refs = [refs[p] for p in shot["refs"]]
            cands = []
            for c in range(spec["candidates"]):
                progress(jd, stage="rendering", done=i, total=total, candidate=c + 1, of=spec["candidates"])
                seed = shot["seed"] + 100 * c
                kw = dict(prompt=shot["request"], width=shot["width"], height=shot["height"],
                          generator=torch.Generator().manual_seed(seed), output=["images", "prompt"])
                if shot_refs:
                    kw["image"] = shot_refs
                res = pipe(**kw)
                cap = res["prompt"] if isinstance(res["prompt"], str) else res["prompt"][0]
                score, defects = judge_image(judge, res["images"][0], shot_refs, shot["scene"], spec["avoid"],
                                               spec.get("checks", [])) \
                    if judge else (None, [])
                cands.append({"img": res["images"][0], "seed": seed, "caption": cap, "score": score, "defects": defects})
                if score is None or (score >= GOOD_ENOUGH and not defects):
                    break
            best = max(cands, key=lambda x: (x["score"] if x["score"] is not None else -1, -len(x["defects"])))
            img = best["img"]
            if not shot["draft"]:
                img.save(f"{out}/{shot['id']}_hd.png")
                rec["hd"] = f"{shot['id']}_hd.png"
            small(img, spec["md_side"]).save(f"{out}/{shot['id']}_md.jpg", quality=92)
            rec["md"] = f"{shot['id']}_md.jpg"
            rec.update(seed=best["seed"], caption=best["caption"], score=best["score"], defects=best["defects"])
            rec["candidates"] = []
            for c in cands:
                info = {"seed": c["seed"], "score": c["score"], "defects": c["defects"]}
                if c is not best:  # the others come back small, so a person can still pick one
                    info["alt"] = f"alts/{shot['id']}-s{c['seed']}.jpg"
                    small(c["img"], spec["md_side"]).save(f"{out}/{info['alt']}", quality=88)
                rec["candidates"].append(info)
        except Exception as e:  # one bad shot must not lose the rest
            rec["error"] = f"{type(e).__name__}: {e}"[:800]
        rec["seconds"] = round(time.time() - t, 1)
        results.append(rec)
        torch.cuda.empty_cache()

    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip()
    json.dump({"gpu": gpu, "job_s": round(time.time() - t_job), "shots": results},
              open(f"{out}/manifest.json", "w"), indent=1)
    with zipfile.ZipFile(f"{jd}/out.zip", "w", zipfile.ZIP_STORED) as z:  # PNG/JPEG are already compressed
        for root, _, files in os.walk(out):
            for name in files:
                z.write(os.path.join(root, name), os.path.relpath(os.path.join(root, name), out))
    progress(jd, stage="finished", done=total, total=total)


def main():
    cfg = json.load(open(f"{W}/worker.json"))
    os.makedirs(f"{W}/jobs", exist_ok=True)
    t0 = time.time()
    try:
        pipe, judge, note = setup(cfg)
    except Exception:
        progress(W, stage="failed", error=traceback.format_exc()[-3000:])
        raise
    progress(W, stage="ready", ready_s=round(time.time() - t0), note=note)
    idle = time.time()
    while time.time() - idle < cfg["idle_exit_s"]:
        beat()
        pending = sorted(d for d in os.listdir(f"{W}/jobs") if os.path.exists(f"{W}/jobs/{d}/spec.json")
                         and not os.path.exists(f"{W}/jobs/{d}/progress.json"))
        if not pending:
            time.sleep(1)
            continue
        jd = f"{W}/jobs/{pending[0]}"
        try:
            run_job(pipe, judge, jd)
        except Exception:
            progress(jd, stage="failed", error=traceback.format_exc()[-3000:])
        idle = time.time()


if __name__ == "__main__":
    main()
